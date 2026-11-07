<template>
  <div class="tools-view">
    <el-card class="tools-card">
      <template #header>
        <div class="tools-header">
          <div>
            <div class="tools-title"><el-icon><Tools /></el-icon>系统工具</div>
            <div class="tools-sub">网络探测、SNMP 调试、子网计算与 SSH 远程终端</div>
          </div>
          <el-tag effect="plain" type="info">在线工具 · 操作需授权</el-tag>
        </div>
      </template>

      <el-tabs v-model="activeTab" class="tools-tabs" @tab-change="onTabChange">
        <el-tab-pane name="snmp">
          <template #label><span class="tab-title"><el-icon><DataLine /></el-icon>SNMP Walk</span></template>
          <div class="tool-intro">
            <div><strong>遍历 SNMP OID 子树</strong><p>支持 v1 / v2c / v3，适合排查设备 OID、验证 MIB 与接口表。</p></div>
            <div class="quick-oids">
              <span>常用 OID</span>
              <el-button link size="small" @click="snmpForm.oid = ''">全量遍历</el-button>
              <el-button v-for="item in quickOids" :key="item.oid" link size="small" @click="snmpForm.oid = item.oid">{{ item.label }}</el-button>
            </div>
          </div>
          <el-form :model="snmpForm" label-position="top" class="tool-form">
            <div class="tool-grid wide">
              <el-form-item label="目标设备">
                <el-input v-model="snmpForm.host" placeholder="IP 或主机名" />
              </el-form-item>
              <el-form-item label="起始 OID（可选）">
                <el-input v-model="snmpForm.oid" clearable placeholder="留空 = 从 1.3.6.1 全量遍历" />
              </el-form-item>
              <el-form-item label="版本">
                <el-select v-model="snmpForm.version">
                  <el-option label="v2c" value="v2c" />
                  <el-option label="v1" value="v1" />
                  <el-option label="v3" value="v3" />
                </el-select>
              </el-form-item>
              <el-form-item v-if="snmpForm.version !== 'v3'" label="团体名">
                <el-input v-model="snmpForm.community" type="password" show-password />
              </el-form-item>
              <el-form-item label="端口">
                <el-input-number v-model="snmpForm.port" :min="1" :max="65535" controls-position="right" />
              </el-form-item>
              <el-form-item label="最多返回">
                <el-input-number v-model="snmpForm.max_rows" :min="10" :max="5000" :step="100" controls-position="right" />
              </el-form-item>
              <el-form-item label="超时（秒）">
                <el-input-number v-model="snmpForm.timeout" :min="1" :max="10" controls-position="right" />
              </el-form-item>
            </div>
            <div v-if="snmpForm.version === 'v3'" class="tool-grid wide">
              <el-form-item label="v3 用户名"><el-input v-model="snmpForm.v3_username" /></el-form-item>
              <el-form-item label="认证密码"><el-input v-model="snmpForm.v3_auth_password" type="password" show-password /></el-form-item>
              <el-form-item label="加密密码"><el-input v-model="snmpForm.v3_priv_password" type="password" show-password /></el-form-item>
            </div>
            <div class="tool-actions">
              <el-button type="primary" :loading="snmpLoading" :disabled="!canEdit" @click="runSnmpwalk">
                <el-icon><CaretRight /></el-icon>开始 Walk
              </el-button>
              <el-button :disabled="!snmpOutput" @click="copy(snmpOutput)">复制结果</el-button>
            </div>
          </el-form>
          <template v-if="snmpResult">
            <div class="result-strip">
              <span>返回 <b>{{ snmpResult.total }}</b> 条</span>
              <span>耗时 <b>{{ snmpResult.duration_ms }}ms</b></span>
              <span v-if="snmpResult.full_walk">全量：从 <b>{{ snmpResult.oid }}</b> 开始</span>
              <span v-if="snmpResult.truncated" class="warn">结果已截断，可调大最多返回条数</span>
            </div>
            <div class="snmp-category-bar">
              <el-button
                size="small"
                :type="snmpCategoryFilter === '' ? 'primary' : ''"
                plain
                @click="snmpCategoryFilter = ''"
              >全部 {{ snmpResult.total }}</el-button>
              <el-button
                v-for="category in snmpResult.categories || []"
                :key="category.key"
                size="small"
                :type="snmpCategoryFilter === category.key ? 'primary' : ''"
                plain
                @click="snmpCategoryFilter = category.key"
              >{{ category.label }} {{ category.count }}</el-button>
            </div>
            <div class="snmp-result-toolbar">
              <span>已选择 <b>{{ snmpSelected.length }}</b> 条</span>
              <div>
                <el-button size="small" :disabled="!snmpSelected.length" @click="copySelectedOids">复制选中</el-button>
                <el-button size="small" type="primary" plain :disabled="!snmpSelected.length" @click="openSnmpAssetDialog">
                  添加选中到资产（{{ snmpSelected.length }}）
                </el-button>
              </div>
            </div>
            <el-table
              ref="snmpTableRef"
              :data="filteredSnmpItems"
              row-key="oid"
              size="small"
              max-height="430"
              class="snmp-result-table"
              @selection-change="snmpSelected = $event"
            >
              <el-table-column type="selection" width="42" />
              <el-table-column label="分类" width="120">
                <template #default="{ row }">
                  <el-tag size="small" effect="plain">{{ row.category_label }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="对象" width="135" show-overflow-tooltip>
                <template #default="{ row }">{{ row.name || '-' }}</template>
              </el-table-column>
              <el-table-column prop="oid" label="OID" min-width="230" show-overflow-tooltip>
                <template #default="{ row }"><span class="mono">{{ row.oid }}</span></template>
              </el-table-column>
              <el-table-column prop="value" label="值" min-width="180" show-overflow-tooltip />
            </el-table>
            <el-collapse v-if="snmpOutput" class="snmp-raw-collapse">
              <el-collapse-item title="查看原始 Walk 输出">
                <pre class="tool-output">{{ snmpOutput }}</pre>
              </el-collapse-item>
            </el-collapse>
          </template>
          <el-empty v-else description="输入设备后开始遍历；起始 OID 可留空进行全量遍历" :image-size="64" />

          <el-dialog v-model="snmpAssetDialog" title="添加选中 OID 到资产" width="620px">
            <el-form label-width="90px">
              <el-form-item label="目标资产">
                <el-select v-model="snmpAssetId" filterable clearable placeholder="选择要添加自定义指标的设备" style="width: 100%">
                  <el-option
                    v-for="device in snmpAssetOptions"
                    :key="device.id"
                    :label="`${device.name}（${device.ip_address}）`"
                    :value="device.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="添加内容">
                <span>已选择 <b>{{ snmpSelected.length }}</b> 条 OID，将写入设备「自定义指标」</span>
              </el-form-item>
              <el-alert
                type="info"
                :closable="false"
                show-icon
                title="同一 OID 不会重复添加；已有自定义指标会保留。分类和名称自动生成，添加后可在设备自定义指标中继续修改。"
              />
            </el-form>
            <template #footer>
              <el-button @click="snmpAssetDialog = false">取消</el-button>
              <el-button type="primary" :loading="snmpAdding" :disabled="!snmpAssetId || !snmpSelected.length" @click="addSnmpMetricsToAsset">添加</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>

        <el-tab-pane name="ping">
          <template #label><span class="tab-title"><el-icon><Position /></el-icon>Ping</span></template>
          <div class="tool-intro"><div><strong>Ping 连通性测试</strong><p>发送指定次数 ICMP 请求，返回丢包率、延迟统计和原始输出。</p></div></div>
          <el-form :model="pingForm" label-position="top" class="tool-form">
            <div class="tool-grid">
              <el-form-item label="目标地址"><el-input v-model="pingForm.host" placeholder="IP 或域名" /></el-form-item>
              <el-form-item label="次数"><el-input-number v-model="pingForm.count" :min="1" :max="20" controls-position="right" /></el-form-item>
              <el-form-item label="单次超时（秒）"><el-input-number v-model="pingForm.timeout" :min="1" :max="10" controls-position="right" /></el-form-item>
              <el-form-item label=" ">
                <el-button type="primary" :loading="pingLoading" :disabled="!canEdit" @click="runPing">开始 Ping</el-button>
              </el-form-item>
            </div>
          </el-form>
          <div v-if="pingResult" class="ping-summary">
            <div><span>目标</span><b>{{ pingResult.host }}</b></div>
            <div :class="pingResult.alive ? 'ok' : 'bad'"><span>状态</span><b>{{ pingResult.alive ? '在线' : '不可达' }}</b></div>
            <div><span>丢包率</span><b>{{ pingResult.loss_percent }}%</b></div>
            <div><span>平均延迟</span><b>{{ pingResult.latency?.avg ?? '-' }} ms</b></div>
          </div>
          <pre v-if="pingResult" class="tool-output">{{ pingResult.output }}</pre>
          <el-empty v-else description="输入目标地址后开始 Ping" :image-size="64" />
        </el-tab-pane>

        <el-tab-pane name="tracert">
          <template #label><span class="tab-title"><el-icon><Guide /></el-icon>Tracert</span></template>
          <div class="tool-intro"><div><strong>路由追踪</strong><p>逐跳探测目标网络路径，支持最大跳数与每跳超时配置。</p></div></div>
          <el-form :model="traceForm" label-position="top" class="tool-form">
            <div class="tool-grid">
              <el-form-item label="目标地址"><el-input v-model="traceForm.host" placeholder="IP 或域名" /></el-form-item>
              <el-form-item label="最大跳数"><el-input-number v-model="traceForm.max_hops" :min="1" :max="64" controls-position="right" /></el-form-item>
              <el-form-item label="每跳超时（秒）"><el-input-number v-model="traceForm.timeout" :min="1" :max="10" controls-position="right" /></el-form-item>
              <el-form-item label=" ">
                <el-button type="primary" :loading="traceLoading" :disabled="!canEdit" @click="runTracert">开始追踪</el-button>
                <el-button v-if="traceLoading" @click="stopTracert">停止</el-button>
              </el-form-item>
            </div>
          </el-form>
          <div v-if="traceLoading || traceResult || traceError" class="trace-live-panel">
            <div class="result-strip">
              <span v-if="traceLoading"><i class="trace-live-dot"></i>实时追踪中 · 已发现 <b>{{ traceLiveHops.length }}</b> 跳</span>
              <span v-else>探测到 <b>{{ traceResult?.hops?.length || 0 }}</b> 个路由节点</span>
              <span v-if="traceResult">耗时 <b>{{ traceResult.duration_ms }}ms</b></span>
              <span v-else-if="traceLoading">每得到一跳结果会立即显示</span>
            </div>
            <div v-if="traceInstall" class="trace-install-panel">
              <div class="trace-install-head">
                <span>{{ traceInstall.status === 'success' ? 'traceroute 安装完成' : '检测到缺少 traceroute，正在自动安装' }}</span>
                <b>{{ traceInstall.progress || 0 }}%</b>
              </div>
              <el-progress
                :percentage="Number(traceInstall.progress || 0)"
                :stroke-width="10"
                :status="traceInstall.status === 'success' ? 'success' : undefined"
              />
              <div class="trace-install-message">{{ traceInstall.message || '正在准备安装...' }}</div>
            </div>
            <el-alert v-if="traceError" :title="traceError" type="error" show-icon :closable="false" />
            <div v-if="traceLiveHops.length" class="trace-hop-list">
              <div v-for="hop in traceLiveHops" :key="hop.hop" class="trace-hop">
                <span>第 {{ hop.hop }} 跳</span>
                <b>{{ hop.ip || '* 超时' }}</b>
              </div>
            </div>
            <pre v-if="traceLiveOutput || traceResult?.output" ref="traceOutputRef" class="tool-output">{{ traceLiveOutput || traceResult?.output }}</pre>
            <div v-else-if="traceLoading" class="trace-waiting">正在等待第一跳响应...</div>
          </div>
          <el-empty v-else description="输入目标地址后开始路由追踪" :image-size="64" />
        </el-tab-pane>

        <el-tab-pane name="publicip">
          <template #label><span class="tab-title"><el-icon><Position /></el-icon>公网 IP</span></template>
          <div class="public-ip-layout">
            <div class="tool-intro">
              <div>
                <strong>当前上网出口 IP</strong>
                <p>查询平台服务器访问互联网时使用的公网 IPv4/IPv6 地址，以及运营商和地区信息。</p>
              </div>
              <el-button type="primary" :loading="publicIpLoading" @click="loadPublicIp(true)">
                <el-icon><Refresh /></el-icon>{{ publicIpResult ? '重新查询' : '查询公网 IP' }}
              </el-button>
            </div>
            <section class="public-ip-card">
              <div class="public-ip-card-head">
                <span>公网出口地址</span>
                <el-tag v-if="publicIpResult?.cached" size="small" type="info" effect="plain">缓存结果</el-tag>
              </div>
              <template v-if="publicIpResult">
                <div class="public-ip-main">
                  <div class="public-ip-value">{{ publicIpResult.ip }}</div>
                  <div class="public-ip-tags">
                    <el-tag size="small" type="success">{{ publicIpResult.version }}</el-tag>
                    <el-tag size="small" type="info">{{ publicIpResult.source }}</el-tag>
                  </div>
                </div>
                <div class="public-ip-grid">
                  <div><span>国家/地区</span><b>{{ [publicIpResult.country, publicIpResult.region, publicIpResult.city].filter(Boolean).join(' · ') || '-' }}</b></div>
                  <div><span>运营商</span><b>{{ publicIpResult.isp || '-' }}</b></div>
                  <div><span>查询耗时</span><b>{{ publicIpResult.duration_ms }} ms</b></div>
                  <div><span>查询时间</span><b>{{ publicIpResult.queried_at || '-' }}</b></div>
                </div>
              </template>
              <el-empty v-else :image-size="58" :description="publicIpLoading ? '正在查询公网出口 IP...' : '点击查询获取平台访问互联网的公网 IP'" />
              <el-alert v-if="publicIpError" type="error" :closable="false" show-icon :title="publicIpError" />
              <p class="public-ip-note">说明：这里显示的是平台服务器所在网络的出口 IP，不是当前浏览器电脑的 IP。</p>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane name="subnet">
          <template #label><span class="tab-title"><el-icon><Grid /></el-icon>子网换算</span></template>
          <div class="subnet-layout">
            <section class="subnet-panel">
              <div class="tool-intro">
                <div>
                  <strong><span class="subnet-proto-badge">IPv4</span> 子网计算器</strong>
                  <p>输入 IP 与掩码位数，实时计算网络地址、广播地址、可用范围和主机数量。</p>
                </div>
              </div>
              <div class="subnet-inputs">
                <el-input v-model="subnet.ip" placeholder="IP 地址" class="subnet-ip" />
                <span class="slash">/</span>
                <el-input-number v-model="subnet.prefix" :min="0" :max="32" controls-position="right" class="subnet-prefix" />
                <span class="subnet-hint">输入 IP 与掩码位数后自动计算</span>
              </div>
              <el-alert v-if="subnetError" :title="subnetError" type="error" show-icon :closable="false" />
              <div v-else class="subnet-results">
                <div class="subnet-big">
                  <span>CIDR</span>
                  <strong>{{ subnetResult.cidr }}</strong>
                  <small>{{ subnetResult.isPrivate ? '私有地址' : '公网地址' }}</small>
                </div>
                <div class="subnet-grid">
                  <div v-for="item in subnetFields" :key="item.label">
                    <span>{{ item.label }}</span>
                    <b>{{ item.value }}</b>
                  </div>
                </div>
                <div class="subnet-binary">
                  <span>网络地址二进制</span>
                  <code>{{ subnetResult.binary }}</code>
                </div>
              </div>
            </section>

            <section class="subnet-panel">
              <div class="tool-intro">
                <div>
                  <strong><span class="subnet-proto-badge ipv6">IPv6</span> 子网计算器</strong>
                  <p>使用 128 位 BigInt 计算 IPv6 网络前缀、最后地址、地址总数与可用地址，支持压缩格式和完整格式。</p>
                </div>
              </div>
              <div class="subnet-inputs">
                <el-input v-model="subnet6.ip" placeholder="2001:db8::1" class="subnet-ip" />
                <span class="slash">/</span>
                <el-input-number v-model="subnet6.prefix" :min="0" :max="128" controls-position="right" class="subnet-prefix" />
                <span class="subnet-hint">支持 :: 压缩格式与 IPv4 映射地址</span>
              </div>
              <el-alert v-if="subnet6Error" :title="subnet6Error" type="error" show-icon :closable="false" />
              <div v-else class="subnet-results">
                <div class="subnet-big">
                  <span>IPv6 CIDR</span>
                  <strong>{{ subnet6Result.cidr }}</strong>
                  <small>{{ subnet6Result.scopeLabel }}</small>
                </div>
                <div class="subnet-grid">
                  <div v-for="item in subnet6Fields" :key="item.label">
                    <span>{{ item.label }}</span>
                    <b>{{ item.value }}</b>
                  </div>
                </div>
                <div class="subnet-binary">
                  <span>网络前缀二进制（128 位）</span>
                  <code>{{ subnet6Result.binary }}</code>
                </div>
              </div>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane name="ssh">
          <template #label><span class="tab-title"><el-icon><Monitor /></el-icon>SSH 终端</span></template>
          <div class="ssh-layout">
            <div class="ssh-panel">
              <div class="ssh-panel-title">连接配置</div>
              <el-form :model="sshForm" label-position="top" class="ssh-form">
                <el-form-item label="主机"><el-input v-model="sshForm.host" placeholder="IP 或域名" /></el-form-item>
                <div class="ssh-inline">
                  <el-form-item label="端口"><el-input-number v-model="sshForm.port" :min="1" :max="65535" controls-position="right" /></el-form-item>
                  <el-form-item label="用户名"><el-input v-model="sshForm.username" placeholder="root" /></el-form-item>
                </div>
                <el-form-item label="认证方式">
                  <el-radio-group v-model="sshForm.authType" size="small">
                    <el-radio-button value="password">密码</el-radio-button>
                    <el-radio-button value="key">私钥</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item v-if="sshForm.authType === 'password'" label="密码">
                  <el-input v-model="sshForm.password" type="password" show-password />
                </el-form-item>
                <template v-else>
                  <el-form-item label="私钥内容">
                    <el-input v-model="sshForm.privateKey" type="textarea" :rows="5" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
                  </el-form-item>
                  <el-form-item label="私钥口令（可选）">
                    <el-input v-model="sshForm.passphrase" type="password" show-password />
                  </el-form-item>
                </template>
                <el-form-item>
                  <el-checkbox v-model="sshForm.acceptNewHostKey">接受未知主机指纹</el-checkbox>
                </el-form-item>
                <div class="ssh-actions">
                  <el-button type="primary" :disabled="sshConnected || !canEdit" :loading="sshConnecting" @click="connectSsh">
                    {{ sshConnecting ? '连接中...' : '连接' }}
                  </el-button>
                  <el-button :disabled="!sshConnected" @click="disconnectSsh">断开</el-button>
                  <el-button :disabled="!terminalReady" @click="clearTerminal">清屏</el-button>
                </div>
                <div class="ssh-status" :class="sshStatusClass"><i></i>{{ sshStatusText }}</div>
              </el-form>
            </div>
            <div class="terminal-panel">
              <div class="terminal-bar">
                <span><i></i><i></i><i></i></span>
                <b>{{ sshForm.username || 'user' }}@{{ sshForm.host || 'host' }}</b>
                <small>xterm-256color</small>
              </div>
              <div ref="terminalRef" class="terminal-host"></div>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane name="sftp">
          <template #label><span class="tab-title"><el-icon><UploadFilled /></el-icon>文件传输</span></template>
          <div class="sftp-layout">
            <div class="sftp-panel">
              <div class="sftp-panel-title">SFTP 连接配置</div>
              <div class="sftp-use-ssh">复用 SSH 终端的主机、用户与认证配置</div>
              <el-form :model="sshForm" label-position="top" class="sftp-form">
                <el-form-item label="主机"><el-input v-model="sshForm.host" placeholder="IP 或域名" /></el-form-item>
                <div class="ssh-inline">
                  <el-form-item label="端口"><el-input-number v-model="sshForm.port" :min="1" :max="65535" controls-position="right" /></el-form-item>
                  <el-form-item label="用户名"><el-input v-model="sshForm.username" placeholder="root" /></el-form-item>
                </div>
                <el-form-item label="认证方式">
                  <el-radio-group v-model="sshForm.authType" size="small">
                    <el-radio-button value="password">密码</el-radio-button>
                    <el-radio-button value="key">私钥</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item v-if="sshForm.authType === 'password'" label="密码">
                  <el-input v-model="sshForm.password" type="password" show-password />
                </el-form-item>
                <template v-else>
                  <el-form-item label="私钥内容">
                    <el-input v-model="sshForm.privateKey" type="textarea" :rows="4" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
                  </el-form-item>
                  <el-form-item label="私钥口令（可选）">
                    <el-input v-model="sshForm.passphrase" type="password" show-password />
                  </el-form-item>
                </template>
                <el-form-item>
                  <el-checkbox v-model="sshForm.acceptNewHostKey">接受未知主机指纹</el-checkbox>
                </el-form-item>
                <el-form-item label="远端目录">
                  <el-input v-model="sftpDir" placeholder="/tmp">
                    <template #prefix><el-icon><FolderOpened /></el-icon></template>
                  </el-input>
                </el-form-item>
                <el-button :loading="sftpListLoading" :disabled="!canEdit" class="sftp-load-btn" @click="loadSftpList">
                  <el-icon><Refresh /></el-icon>读取目录
                </el-button>
                <div class="ssh-status" :class="sftpStatusClass"><i></i>{{ sftpStatusText }}</div>
              </el-form>
            </div>

            <div class="sftp-main">
              <div class="sftp-upload-card" :class="{ 'is-dragging': sftpDragging }" @dragover.prevent="sftpDragging = true" @dragleave.prevent="sftpDragging = false" @drop.prevent="onSftpDrop">
                <input ref="sftpFileRef" type="file" class="sftp-hidden-input" @change="onSftpFileChange" />
                <div class="sftp-upload-icon"><el-icon><UploadFilled /></el-icon></div>
                <div class="sftp-upload-copy">
                  <strong>{{ sftpFile ? sftpFile.name : '选择或拖入文件' }}</strong>
                  <small>{{ sftpFile ? `${formatSize(sftpFile.size)} · 将上传到 ${sftpDir}` : '支持任意文件类型，单个文件最大 200MB' }}</small>
                </div>
                <el-button :disabled="sftpUploading" @click="pickSftpFile">选择文件</el-button>
                <el-button type="primary" :loading="sftpUploading" :disabled="!sftpFile || !canEdit" @click="uploadSftpFile">
                  <el-icon><Upload /></el-icon>上传到 Linux
                </el-button>
                <el-button v-if="sftpFile" link :disabled="sftpUploading" @click="clearSftpFile">清除</el-button>
                <div v-if="sftpUploading || sftpUploadPercent" class="sftp-progress">
                  <el-progress :percentage="sftpUploadPercent" :stroke-width="6" />
                </div>
              </div>

              <div class="sftp-list-card">
                <div class="sftp-list-head">
                  <div class="sftp-location">
                    <strong>远端文件</strong>
                    <span>{{ sftpDir }}</span>
                    <small>点击文件夹进入下一级</small>
                  </div>
                  <div class="sftp-list-actions">
                    <el-button size="small" :disabled="isSftpRoot" @click="goSftpParent">
                      <el-icon><Top /></el-icon>上一级
                    </el-button>
                    <el-button size="small" :loading="sftpListLoading" @click="loadSftpList">
                      <el-icon><Refresh /></el-icon>刷新
                    </el-button>
                  </div>
                </div>
                <el-table
                  :data="sftpFiles"
                  size="small"
                  max-height="360"
                  empty-text="目录暂无文件"
                  :row-class-name="sftpRowClass"
                  @row-click="onSftpRowClick"
                >
                  <el-table-column label="名称" min-width="220">
                    <template #default="{ row }">
                      <span class="sftp-name" :class="{ folder: row.is_dir }">
                        <el-icon><FolderOpened v-if="row.is_dir" /><Document v-else /></el-icon>
                        {{ row.name }}
                        <em v-if="row.is_dir" class="sftp-enter-hint">进入</em>
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column label="大小" width="100">
                    <template #default="{ row }">{{ row.is_dir ? '-' : formatSize(row.size) }}</template>
                  </el-table-column>
                  <el-table-column label="修改时间" width="170">
                    <template #default="{ row }">{{ formatSftpTime(row.modified) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="90">
                    <template #default="{ row }">
                      <el-button v-if="row.is_dir" link @click.stop="enterSftpDirectory(row)">进入</el-button>
                      <el-button v-else link :disabled="!canEdit" @click.stop="downloadSftpFile(row)">下载</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane name="capture">
          <template #label><span class="tab-title"><el-icon><DataAnalysis /></el-icon>网络抓包</span></template>
          <div class="capture-layout">
            <div class="capture-config panel">
              <div class="capture-config-head">
                <div>
                  <strong>实时抓包与异常定位</strong>
                  <span>保存 Wireshark 兼容 .cap（含原始报文）；分析面板仅展示报文头聚合与异常特征</span>
                </div>
                <el-tag :type="captureCapability?.available ? 'success' : 'danger'" effect="plain" size="small">
                  {{ captureCapability?.available ? (captureCapability.backend === 'npcap' ? 'Npcap 就绪' : '抓包引擎就绪') : '抓包不可用' }}
                </el-tag>
              </div>
              <div class="capture-form-row">
                <label class="capture-field capture-interface">
                  <span>抓包网卡</span>
                  <el-select v-model="captureInterface" filterable placeholder="选择网卡" :loading="captureInterfacesLoading" :disabled="captureRunning || !canEdit">
                    <el-option
                      v-for="item in captureInterfaces"
                      :key="item.id"
                      :label="item.label || item.name || item.id"
                      :value="item.id"
                    >
                      <div class="capture-if-option">
                        <span>{{ item.label || item.name }}</span>
                        <small>{{ item.ips?.join(' · ') || '无 IP' }} · {{ item.mac || '无 MAC' }}</small>
                      </div>
                    </el-option>
                  </el-select>
                </label>
                <label class="capture-field">
                  <span>时长</span>
                  <el-input-number v-model="captureDuration" :min="1" :max="300" :step="5" :disabled="captureRunning || !canEdit" controls-position="right" />
                  <small>秒</small>
                </label>
                <label class="capture-field">
                  <span>最大报文</span>
                  <el-input-number v-model="captureMaxPackets" :min="10" :max="200000" :step="1000" :disabled="captureRunning || !canEdit" controls-position="right" />
                </label>
                <label class="capture-field capture-filter">
                  <span>BPF 过滤（可选）</span>
                  <el-input v-model="captureFilter" placeholder="例如：tcp or icmp" :disabled="captureRunning || !canEdit" />
                </label>
                <el-button type="primary" :loading="captureStarting" :disabled="!canEdit || captureRunning" @click="startCapture">
                  <el-icon><VideoPlay /></el-icon>开始抓包
                </el-button>
                <el-button v-if="captureRunning" type="danger" plain :loading="captureStarting" @click="stopCapture">
                  <el-icon><VideoPause /></el-icon>停止
                </el-button>
              </div>
              <div class="capture-config-hint">
                <span>需要在服务器安装 Npcap（Windows）或以管理员权限运行；抓包过程中访问 {{ captureInterfaceLabel || '目标网卡' }} 的所有流量。</span>
                <el-button link @click="loadCaptureInterfaces" :loading="captureInterfacesLoading">刷新网卡</el-button>
              </div>
              <el-alert v-if="captureCapability && !captureCapability.available" type="error" :closable="false" show-icon :title="captureCapability.message" />
              <el-alert v-if="captureError" type="error" :closable="false" show-icon :title="captureError" />
              <el-alert v-if="captureJob?.save_error" type="warning" :closable="false" show-icon :title="`分析报告保存失败：${captureJob.save_error}`" />
            </div>

            <template v-if="captureJob">
              <div class="capture-metrics">
                <div class="capture-metric"><span>抓包状态</span><b :class="captureStatusClass">{{ captureStatusText }}</b></div>
                <div class="capture-metric"><span>报文</span><b>{{ captureJob.packets?.toLocaleString() }}</b></div>
                <div class="capture-metric"><span>流量</span><b>{{ formatSize(captureJob.bytes) }}</b></div>
                <div class="capture-metric"><span>速率</span><b>{{ captureJob.throughput_mbps }} <small>Mbps</small></b></div>
                <div class="capture-metric"><span>错误/广播</span><b>{{ captureJob.errors }} / {{ captureJob.broadcast_packets }}</b></div>
                <div class="capture-metric"><span>唯一 IP / MAC</span><b>{{ captureJob.unique_ips }} / {{ captureJob.unique_macs }}</b></div>
              </div>

              <div class="capture-analysis-grid">
                <div class="capture-findings panel">
                  <div class="capture-section-head">
                    <div><strong><el-icon><WarningFilled /></el-icon>异常定位</strong><span>按攻击特征与流量占比给出可核查对象</span></div>
                    <el-tag v-if="captureRunning" type="success" effect="plain" size="small">实时更新</el-tag>
                  </div>
                  <el-table :data="captureJob.findings || []" size="small" empty-text="分析中..." max-height="320">
                    <el-table-column label="级别" width="74">
                      <template #default="{ row }">
                        <el-tag :type="captureSeverityType(row.severity)" size="small" effect="dark">{{ captureSeverityText(row.severity) }}</el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column label="异常特征" min-width="160">
                      <template #default="{ row }">
                        <strong class="capture-finding-title">{{ row.title }}</strong>
                        <small class="capture-finding-desc">{{ row.description }}</small>
                      </template>
                    </el-table-column>
                    <el-table-column label="IP / MAC" min-width="190">
                      <template #default="{ row }">
                        <span class="capture-mono">{{ row.ip || '-' }}</span>
                        <span class="capture-mac">{{ row.mac || '-' }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="设备 / 接口" min-width="170">
                      <template #default="{ row }">
                        <span v-if="row.device_name" class="capture-device">{{ row.device_name }}</span>
                        <span v-else class="capture-unmatched">未匹配资产</span>
                        <small>{{ row.interface_name || row.interface_description || row.capture_interface || '采集接口' }}</small>
                      </template>
                    </el-table-column>
                    <el-table-column prop="evidence" label="证据" min-width="130" show-overflow-tooltip />
                  </el-table>
                </div>
                <div class="capture-side panel">
                  <div class="capture-section-head"><div><strong>协议与 TCP 标记</strong><span>当前抓包窗口</span></div></div>
                  <div class="capture-protocols">
                    <span v-for="(count, name) in captureJob.protocols || {}" :key="name" class="capture-protocol">
                      <b>{{ name }}</b><em>{{ count }}</em>
                    </span>
                  </div>
                  <div class="capture-flags">
                    <span v-for="(count, name) in captureJob.tcp_flags || {}" :key="name">{{ name }} <b>{{ count }}</b></span>
                    <span v-if="!Object.keys(captureJob.tcp_flags || {}).length">暂无 TCP</span>
                  </div>
                  <div class="capture-side-foot">
                    错误率 <b>{{ captureJob.error_percent }}%</b> · 广播率 <b>{{ captureJob.broadcast_percent }}%</b> · SYN-only <b>{{ captureJob.syn_only }}</b>
                  </div>
                </div>
              </div>

              <div class="capture-talkers-grid">
                <div class="panel capture-talker-card">
                  <div class="capture-section-head"><div><strong>源 IP 流量 TOP</strong><span>快速定位大流量发送方</span></div></div>
                  <el-table :data="captureJob.top_sources || []" size="small" max-height="300" empty-text="等待流量...">
                    <el-table-column label="IP / MAC" min-width="170">
                      <template #default="{ row }"><span class="capture-mono">{{ row.ip }}</span><small class="capture-mac">{{ row.mac || '-' }}</small></template>
                    </el-table-column>
                    <el-table-column label="资产 / 接口" min-width="160">
                      <template #default="{ row }">
                        <span v-if="row.device_name" class="capture-device">{{ row.device_name }}</span>
                        <span v-else class="capture-unmatched">未匹配资产</span>
                        <small>{{ row.interface_name || row.capture_interface }}</small>
                      </template>
                    </el-table-column>
                    <el-table-column prop="packets" label="报文" width="80" />
                    <el-table-column label="流量" width="90"><template #default="{ row }">{{ formatSize(row.bytes) }}</template></el-table-column>
                    <el-table-column label="占比" width="70"><template #default="{ row }">{{ row.share }}%</template></el-table-column>
                  </el-table>
                </div>
                <div class="panel capture-talker-card">
                  <div class="capture-section-head"><div><strong>目标 IP / 端口 TOP</strong><span>快速定位被访问对象与异常端口</span></div></div>
                  <el-table :data="captureJob.top_destinations || []" size="small" max-height="240" empty-text="等待流量...">
                    <el-table-column label="目标 IP / 设备" min-width="170">
                      <template #default="{ row }"><span class="capture-mono">{{ row.ip }}</span><small>{{ row.device_name || row.interface_name || '未匹配资产' }}</small></template>
                    </el-table-column>
                    <el-table-column prop="packets" label="报文" width="80" />
                    <el-table-column label="流量" width="90"><template #default="{ row }">{{ formatSize(row.bytes) }}</template></el-table-column>
                    <el-table-column label="占比" width="70"><template #default="{ row }">{{ row.share }}%</template></el-table-column>
                  </el-table>
                  <div class="capture-port-list">
                    <span v-for="port in (captureJob.top_ports || []).slice(0, 8)" :key="port.port">{{ port.port }} <b>{{ port.packets }}</b></span>
                  </div>
                </div>
              </div>
            </template>
            <div v-else class="capture-empty panel">
              <div class="capture-empty-icon"><el-icon><DataAnalysis /></el-icon></div>
              <strong>选择网卡后开始抓包</strong>
              <p>系统将按报文头部聚合源/目标 IP、MAC、TCP 错误标记、协议、端口和流量占比，并在异常特征中定位可疑设备与接口。</p>
            </div>
            <div class="capture-history panel">
              <div class="capture-history-head">
                <div>
                  <strong><el-icon><Files /></el-icon>抓包文件记录</strong>
                  <span>完成后自动保存 Wireshark 兼容 .cap 文件，并另存 JSON 分析报告；.cap 包含原始报文，请妥善保管</span>
                </div>
                <div class="capture-history-actions">
                  <el-button size="small" :loading="captureRecordsLoading" @click="loadCaptureRecords">刷新</el-button>
                  <el-button size="small" :disabled="!captureRecordSelection.length" @click="saveSelectedCaptureRecords">
                    <el-icon><Download /></el-icon>批量保存
                  </el-button>
                  <el-button size="small" type="danger" plain :disabled="!captureRecordSelection.length" @click="deleteSelectedCaptureRecords">
                    <el-icon><Delete /></el-icon>批量删除
                  </el-button>
                </div>
              </div>
              <el-table
                ref="captureRecordTableRef"
                :data="captureRecords"
                size="small"
                border
                max-height="280"
                empty-text="暂无抓包文件，完成一次抓包后自动保存 .cap"
                @selection-change="onCaptureRecordSelection"
              >
                <el-table-column type="selection" width="42" />
                <el-table-column label="抓包文件" min-width="245">
                  <template #default="{ row }"><span class="capture-record-name">{{ row.filename }}</span></template>
                </el-table-column>
                <el-table-column prop="interface_label" label="抓包网卡" min-width="155" show-overflow-tooltip />
                <el-table-column label="开始时间" width="150">
                  <template #default="{ row }">{{ (row.started_at || '').replace('T', ' ').slice(0, 19) }}</template>
                </el-table-column>
                <el-table-column label="报文 / 流量" width="125">
                  <template #default="{ row }">{{ row.packets?.toLocaleString() }} / {{ formatSize(row.bytes) }}</template>
                </el-table-column>
                <el-table-column label="异常特征" width="76">
                  <template #default="{ row }">{{ row.findings_count || 0 }}</template>
                </el-table-column>
                <el-table-column label="文件大小" width="82">
                  <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
                </el-table-column>
                <el-table-column label="状态" width="72">
                  <template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : 'info'" size="small">{{ row.status === 'completed' ? '完成' : '停止' }}</el-tag></template>
                </el-table-column>
                <el-table-column label="操作" width="118" fixed="right">
                  <template #default="{ row }">
                    <el-button link size="small" @click="downloadCaptureRecord(row)">下载</el-button>
                    <el-button link type="danger" size="small" @click="deleteCaptureRecord(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane name="notes">
          <template #label><span class="tab-title"><el-icon><Notebook /></el-icon>运维笔记</span></template>
          <div class="notes-layout">
            <aside class="notes-side">
              <div class="notes-side-head">
                <div>
                  <strong>运维笔记</strong>
                  <span>{{ notesTab === 'mine' ? `${filteredNotes.length} 条` : `${sharedNotes.length} 条` }}</span>
                </div>
                <el-button type="primary" size="small" @click="newNote">
                  <el-icon><Plus /></el-icon>新建
                </el-button>
              </div>
              <el-radio-group v-model="notesTab" size="small" class="notes-tabs" @change="onNotesTabChange">
                <el-radio-button value="mine">我的笔记</el-radio-button>
                <el-radio-button value="shared">分享给我的</el-radio-button>
              </el-radio-group>
              <el-input v-model="noteSearch" size="small" clearable placeholder="搜索标题或内容" class="notes-search">
                <template #prefix><el-icon><Search /></el-icon></template>
              </el-input>

              <template v-if="notesTab === 'mine'">
                <div class="notes-batch-bar">
                  <el-checkbox
                    :model-value="filteredNotes.length > 0 && selectedNoteIds.length === filteredNotes.length"
                    :indeterminate="selectedNoteIds.length > 0 && selectedNoteIds.length < filteredNotes.length"
                    @change="toggleSelectAllNotes"
                  >全选</el-checkbox>
                  <el-button link type="danger" :disabled="!selectedNoteIds.length" @click="batchDeleteNotes">批量删除({{ selectedNoteIds.length }})</el-button>
                  <el-button link type="primary" :disabled="!selectedNoteIds.length" @click="batchShareNotes">批量分享({{ selectedNoteIds.length }})</el-button>
                </div>
                <div class="notes-list">
                  <div
                    v-for="note in filteredNotes"
                    :key="note.id"
                    class="note-item"
                    :class="{ active: selectedNote?.id === note.id }"
                    @click="selectNote(note, false)"
                  >
                    <el-checkbox
                      :model-value="selectedNoteIds.includes(note.id)"
                      class="note-check"
                      @click.stop
                      @change="toggleSelectNote(note.id)"
                    />
                    <div class="note-item-main">
                      <div class="note-item-title">
                        <span>{{ note.title }}</span>
                        <em>{{ note.note_format === 'markdown' ? 'MD' : 'TXT' }}</em>
                      </div>
                      <div class="note-item-meta">
                        <span>{{ formatNoteTime(note.updated_at) }}</span>
                        <span v-if="note.shared_to?.length">已分享 {{ note.shared_to.length }} 人</span>
                      </div>
                    </div>
                  </div>
                  <el-empty v-if="!filteredNotes.length" description="还没有个人笔记" :image-size="48" />
                </div>
              </template>

              <template v-else>
                <div class="notes-list">
                  <div
                    v-for="note in filteredSharedNotes"
                    :key="note.id"
                    class="note-item shared-note"
                    :class="{ active: selectedNote?.id === note.id }"
                    @click="selectNote(note, true)"
                  >
                    <div class="note-item-main">
                      <div class="note-item-title">
                        <span>{{ note.title }}</span>
                        <em>{{ note.note_format === 'markdown' ? 'MD' : 'TXT' }}</em>
                      </div>
                      <div class="note-item-meta">
                        <span>{{ note.owner_name || '其他用户' }} · {{ formatNoteTime(note.updated_at) }}</span>
                      </div>
                    </div>
                    <el-button link type="primary" size="small" @click.stop="saveSharedNote(note)">保存副本</el-button>
                  </div>
                  <el-empty v-if="!filteredSharedNotes.length" description="暂无分享给你的笔记" :image-size="48" />
                </div>
              </template>
            </aside>

            <section class="notes-editor">
              <template v-if="noteFormActive">
                <div class="notes-editor-head">
                  <div class="notes-editor-title">
                    <span>{{ selectedNote && !selectedNote.is_owner ? '共享笔记' : (selectedNote ? '编辑笔记' : '新建笔记') }}</span>
                    <el-tag v-if="selectedNote && !selectedNote.is_owner" size="small" type="warning" effect="plain">只读</el-tag>
                    <el-tag v-else size="small" type="info" effect="plain">{{ noteForm.note_format === 'markdown' ? 'Markdown' : '普通文本' }}</el-tag>
                  </div>
                  <div class="notes-editor-actions">
                    <el-button size="small" :disabled="!!(selectedNote && !selectedNote.is_owner)" @click="notePreview = !notePreview">
                      <el-icon><View /></el-icon>{{ notePreview ? '编辑内容' : '预览' }}
                    </el-button>
                    <el-button v-if="canEditNote" size="small" :disabled="!!(selectedNote && !selectedNote.is_owner)" :loading="noteSaving" type="primary" @click="saveNote">
                      <el-icon><Check /></el-icon>保存
                    </el-button>
                    <el-button v-if="canEditNote" size="small" :disabled="!selectedNote || !selectedNote.is_owner" @click="openShareDialog([selectedNote.id])">
                      <el-icon><Share /></el-icon>分享
                    </el-button>
                    <el-button v-if="canEditNote" size="small" type="danger" plain :disabled="!selectedNote || !selectedNote.is_owner" @click="deleteCurrentNote">
                      <el-icon><Delete /></el-icon>删除
                    </el-button>
                    <el-button v-if="selectedNote && !selectedNote.is_owner" size="small" type="primary" @click="saveSharedNote(selectedNote)">
                      <el-icon><Download /></el-icon>保存到我的笔记
                    </el-button>
                  </div>
                </div>
                <div class="notes-format-row">
                  <el-radio-group v-model="noteForm.note_format" size="small" :disabled="!!(selectedNote && !selectedNote.is_owner)">
                    <el-radio-button value="markdown">Markdown</el-radio-button>
                    <el-radio-button value="plain">普通文本</el-radio-button>
                  </el-radio-group>
                  <span v-if="selectedNote && selectedNote.is_owner" class="notes-share-info">
                    分享给：{{ selectedNote.shared_to?.length ? selectedNote.shared_to.map((u) => u.real_name || u.username).join('、') : '未分享' }}
                  </span>
                  <span v-else-if="selectedNote" class="notes-share-info">
                    来自 {{ selectedNote.owner_name || '其他用户' }}，只读；保存副本后可编辑
                  </span>
                </div>
                <el-input v-model="noteForm.title" maxlength="200" placeholder="笔记标题，例如：核心交换机端口闪断排查" class="notes-title-input" :disabled="!!(selectedNote && !selectedNote.is_owner)" />
                <div v-if="!notePreview" class="notes-content-editor">
                  <el-input v-model="noteForm.content" type="textarea" :rows="16" resize="none" :disabled="!!(selectedNote && !selectedNote.is_owner)"
                    :placeholder="noteForm.note_format === 'markdown' ? '支持 Markdown：# 标题、**加粗**、`代码`、- 列表、```代码块```' : '记录故障现象、排查过程和解决方案...'" />
                </div>
                <div v-else class="notes-preview">
                  <div v-if="noteForm.note_format === 'markdown'" class="markdown-body" v-html="renderMarkdown(noteForm.content)"></div>
                  <pre v-else>{{ noteForm.content || '暂无内容' }}</pre>
                </div>
                <div class="notes-editor-foot">
                  <span>{{ noteForm.content.length }} 字符</span>
                  <span v-if="selectedNote">最近更新 {{ formatNoteTime(selectedNote.updated_at) }}</span>
                </div>
              </template>
              <el-empty v-else description="选择左侧笔记，或点击「新建」开始记录" :image-size="70" />
            </section>
          </div>
        </el-tab-pane>
        <el-tab-pane name="floatingball">
          <template #label><span class="tab-title"><el-icon><Mouse /></el-icon>悬浮球设置</span></template>
          <FloatingBallSettings />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="shareVisible" title="分享运维笔记" width="480px" :close-on-click-modal="false">
      <div class="share-dialog-info">
        已选择 <b>{{ shareTargetIds.length }}</b> 条笔记，选择要分享给的用户：
      </div>
      <el-select v-model="shareUserIds" multiple filterable clearable placeholder="选择用户" style="width:100%">
        <el-option
          v-for="user in shareUsers"
          :key="user.id"
          :label="`${user.real_name || user.username}（${user.username}）`"
          :value="user.id"
        />
      </el-select>
      <div class="share-dialog-hint">
        被分享用户可以查看和保存副本，但不能修改或删除原笔记；保存后会覆盖这些笔记原有的分享名单。
        清空用户并保存表示取消分享。
      </div>
      <template #footer>
        <el-button @click="shareVisible = false">取消</el-button>
        <el-button type="primary" :loading="shareSaving" @click="confirmShare">确认分享</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { toolsApi, notesApi, assetApi } from '@/api'
import { can, getToken } from '@/store/auth'
import FloatingBallSettings from '@/components/FloatingBallSettings.vue'

const activeTab = ref('snmp')
const route = useRoute()
onMounted(() => {
  const tab = String(route.query.tab || '')
  if (tab) activeTab.value = tab
  if (tab === 'publicip') loadPublicIp(false)
})
const canEdit = computed(() => can('tools:edit'))
const canEditNote = computed(() => can('tools:view'))
const notesTab = ref('mine')
const notes = ref([])
const sharedNotes = ref([])
const noteSearch = ref('')
const notesLoading = ref(false)
const selectedNote = ref(null)
const selectedNoteIds = ref([])
const noteForm = reactive({ title: '', content: '', note_format: 'markdown' })
const noteFormActive = ref(false)
const notePreview = ref(false)
const noteSaving = ref(false)
const shareVisible = ref(false)
const shareSaving = ref(false)
const shareTargetIds = ref([])
const shareUserIds = ref([])
const shareUsers = ref([])
const filteredNotes = computed(() => {
  const keyword = noteSearch.value.trim().toLowerCase()
  if (!keyword) return notes.value
  return notes.value.filter((note) => `${note.title} ${note.content}`.toLowerCase().includes(keyword))
})
const filteredSharedNotes = computed(() => {
  const keyword = noteSearch.value.trim().toLowerCase()
  if (!keyword) return sharedNotes.value
  return sharedNotes.value.filter((note) => `${note.title} ${note.content} ${note.owner_name || ''}`.toLowerCase().includes(keyword))
})

const quickOids = [
  { label: '系统信息', oid: '1.3.6.1.2.1.1' },
  { label: '接口表', oid: '1.3.6.1.2.1.2.2.1' },
  { label: 'IP 地址表', oid: '1.3.6.1.2.1.4.20.1' },
  { label: 'ARP 表', oid: '1.3.6.1.2.1.4.22.1' },
  { label: 'LLDP 邻居', oid: '1.0.8802.1.1.2.1.4.1.1' },
]

const snmpForm = reactive({
  host: '', oid: '', version: 'v2c', community: 'public',
  port: 161, timeout: 3, max_rows: 1000,
  v3_username: '', v3_auth_password: '', v3_priv_password: '',
})
const snmpLoading = ref(false)
const snmpResult = ref(null)
const snmpOutput = ref('')
const snmpSelected = ref([])
const snmpTableRef = ref(null)
const snmpCategoryFilter = ref('')
const snmpAssetDialog = ref(false)
const snmpAssetId = ref(null)
const snmpAssetOptions = ref([])
const snmpAdding = ref(false)
const filteredSnmpItems = computed(() => {
  const items = snmpResult.value?.items || []
  if (!snmpCategoryFilter.value) return items
  return items.filter((item) => item.category === snmpCategoryFilter.value)
})

const pingForm = reactive({ host: '', count: 4, timeout: 5 })
const pingLoading = ref(false)
const pingResult = ref(null)

const traceForm = reactive({ host: '', max_hops: 30, timeout: 5 })
const publicIpLoading = ref(false)
const publicIpResult = ref(null)
const publicIpError = ref('')
const traceLoading = ref(false)
const traceResult = ref(null)
const traceError = ref('')
const traceLiveOutput = ref('')
const traceLiveHops = ref([])
const traceInstall = ref(null)
const traceOutputRef = ref(null)
let traceSocket = null
let traceFinished = false

const subnet = reactive({ ip: '192.168.1.10', prefix: 24 })
const subnetResult = computed(() => calculateSubnet(subnet.ip, subnet.prefix))
const subnetError = computed(() => subnetResult.value?.error || '')
const subnetFields = computed(() => {
  const result = subnetResult.value
  if (!result || result.error) return []
  return [
    { label: '子网掩码', value: result.mask },
    { label: '反掩码', value: result.wildcard },
    { label: '网络地址', value: result.network },
    { label: '广播地址', value: result.broadcast },
    { label: '可用范围', value: result.range },
    { label: '可用主机数', value: result.hosts.toLocaleString() },
  ]
})

const subnet6 = reactive({ ip: '2001:db8::1', prefix: 64 })
const subnet6Result = computed(() => calculateSubnet6(subnet6.ip, subnet6.prefix))
const subnet6Error = computed(() => subnet6Result.value?.error || '')
const subnet6Fields = computed(() => {
  const result = subnet6Result.value
  if (!result || result.error) return []
  return [
    { label: '压缩地址', value: result.compressed },
    { label: '完整地址', value: result.expanded },
    { label: '子网掩码', value: result.mask },
    { label: '网络前缀', value: result.cidr },
    { label: '最后地址', value: result.last },
    { label: '地址总数', value: result.totalText },
    { label: '可用地址（不含网络地址）', value: result.usableText },
    { label: '地址类型', value: result.scopeLabel },  ]
})

const sshForm = reactive({
  host: '', port: 22, username: '', password: '', privateKey: '', passphrase: '',
  authType: 'password', acceptNewHostKey: true,
})
const sshConnecting = ref(false)
const sshConnected = ref(false)
const sshStatusText = ref('未连接')
const sshStatusClass = ref('idle')
const terminalRef = ref(null)
const terminalReady = ref(false)
const sftpFileRef = ref(null)
const captureInterfaces = ref([])
const captureInterfacesLoading = ref(false)
const captureCapability = ref(null)
const captureInterface = ref('')
const captureDuration = ref(30)
const captureMaxPackets = ref(50000)
const captureFilter = ref('')
const captureJob = ref(null)
const captureStarting = ref(false)
const captureError = ref('')
const captureRecords = ref([])
const captureRecordsLoading = ref(false)
const captureRecordSelection = ref([])
const captureRecordTableRef = ref(null)
let capturePollTimer = null
const captureRunning = computed(() => ['starting', 'running', 'stopping'].includes(captureJob.value?.status))
const captureInterfaceLabel = computed(() => {
  const found = captureInterfaces.value.find((item) => item.id === captureInterface.value)
  return found?.label || found?.name || captureInterface.value
})
const captureStatusText = computed(() => ({
  starting: '启动中', running: '抓包中', stopping: '停止中', stopped: '已停止', completed: '已完成', error: '异常',
}[captureJob.value?.status] || '未开始'))
const captureStatusClass = computed(() => ({
  running: 'capture-live', completed: 'capture-ok', stopped: 'capture-ok', error: 'capture-error',
}[captureJob.value?.status] || ''))
const sftpFile = ref(null)
const sftpDir = ref('/tmp')
const isSftpRoot = computed(() => normalizeSftpPath(sftpDir.value) === '/')
const sftpFiles = ref([])
const sftpListLoading = ref(false)
const sftpUploading = ref(false)
const sftpUploadPercent = ref(0)
const sftpDragging = ref(false)
const sftpStatusText = ref('未读取目录')
const sftpStatusClass = ref('idle')
let terminal = null
let fitAddon = null
let socket = null
let resizeObserver = null
let reconnectTimer = null

function errorMessage(error) {
  return error?.response?.data?.detail || error?.message || '操作失败'
}

function formatSnmpOutput(result) {
  const target = result.requested_oid ? result.requested_oid : `${result.oid}（全量）`
  if (!result.items?.length) return `# ${result.host} ${target}\n无返回结果（OID 可能不存在或无权限）`
  return result.items.map((item) => `${item.oid} = ${item.value}`).join('\n')
}

function metricKeyForOid(oid, usedKeys) {
  const tail = String(oid || '').replace(/[^0-9a-zA-Z]+/g, '_').replace(/^_+|_+$/g, '')
  const base = (`walk_${tail || 'metric'}`).slice(0, 30)
  let key = base
  let index = 2
  while (usedKeys.has(key)) {
    const suffix = `_${index}`
    key = `${base.slice(0, 30 - suffix.length)}${suffix}`
    index += 1
  }
  usedKeys.add(key)
  return key
}

async function copySelectedOids() {
  if (!snmpSelected.value.length) return
  await copy(snmpSelected.value.map((item) => `${item.oid} = ${item.value}`).join('\n'))
}

async function openSnmpAssetDialog() {
  if (!snmpSelected.value.length) return
  snmpAssetDialog.value = true
  if (snmpAssetOptions.value.length) return
  try {
    const { data } = await assetApi.getList({ page: 1, size: 100 })
    snmpAssetOptions.value = data.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function addSnmpMetricsToAsset() {
  if (!snmpAssetId.value || !snmpSelected.value.length) return
  snmpAdding.value = true
  try {
    const { data } = await assetApi.getOne(snmpAssetId.value)
    const metrics = Array.isArray(data.custom_metrics) ? [...data.custom_metrics] : []
    const usedKeys = new Set(metrics.map((item) => item.key))
    const existingOids = new Set(metrics.map((item) => item.oid))
    let added = 0
    let skipped = 0
    for (const item of snmpSelected.value) {
      if (existingOids.has(item.oid)) {
        skipped += 1
        continue
      }
      if (metrics.length >= 20) {
        skipped += 1
        continue
      }
      const key = metricKeyForOid(item.oid, usedKeys)
      metrics.push({
        key,
        name: (item.name || `${item.category_label} ${item.oid.split('.').slice(-3).join('.')}`).slice(0, 60),
        oid: item.oid,
        unit: '',
        scale: 1,
      })
      existingOids.add(item.oid)
      added += 1
    }
    if (!added) {
      ElMessage.warning(skipped ? '选中 OID 已存在或设备自定义指标已满 20 个' : '没有可添加的 OID')
      return
    }
    await assetApi.update(snmpAssetId.value, { custom_metrics: metrics })
    ElMessage.success(`已添加 ${added} 个自定义指标${skipped ? `，跳过 ${skipped} 条` : ''}`)
    snmpAssetDialog.value = false
    snmpAssetId.value = null
    snmpSelected.value = []
    snmpTableRef.value?.clearSelection()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    snmpAdding.value = false
  }
}

async function runSnmpwalk() {
  if (!snmpForm.host.trim()) { ElMessage.warning('请输入目标设备'); return }
  const oid = snmpForm.oid.trim()
  if (oid && !/^\d+(\.\d+)*$/.test(oid)) { ElMessage.warning('OID 必须是数字点分格式，留空可全量遍历'); return }
  snmpLoading.value = true
  snmpSelected.value = []
  snmpCategoryFilter.value = ''
  snmpTableRef.value?.clearSelection()
  try {
    const { data } = await toolsApi.snmpwalk({ ...snmpForm, oid })
    snmpResult.value = data
    snmpOutput.value = formatSnmpOutput(data)
    ElMessage.success(`Walk 完成，共 ${data.total} 条${data.full_walk ? '（全量）' : ''}`)
  } catch (error) {
    snmpResult.value = null
    snmpOutput.value = ''
    ElMessage.error(errorMessage(error))
  } finally { snmpLoading.value = false }
}

async function runPing() {
  if (!pingForm.host.trim()) { ElMessage.warning('请输入目标地址'); return }
  pingLoading.value = true
  try {
    const { data } = await toolsApi.ping({ ...pingForm })
    pingResult.value = data
    ElMessage.success(data.alive ? '目标在线' : '目标不可达')
  } catch (error) {
    pingResult.value = null
    ElMessage.error(errorMessage(error))
  } finally { pingLoading.value = false }
}

function closeTraceSocket() {
  if (traceSocket) {
    try { traceSocket.close() } catch { /* ignore */ }
    traceSocket = null
  }
}

function stopTracert() {
  traceFinished = true
  traceLoading.value = false
  closeTraceSocket()
  ElMessage.info('已停止实时路由追踪')
}

async function runTracert() {
  if (!traceForm.host.trim()) { ElMessage.warning('请输入目标地址'); return }
  closeTraceSocket()
  traceFinished = false
  traceLoading.value = true
  traceResult.value = null
  traceError.value = ''
  traceLiveOutput.value = ''
  traceLiveHops.value = []
  traceInstall.value = null
  try {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    traceSocket = new WebSocket(`${scheme}://${window.location.host}/api/tools/tracert/ws`)
    traceSocket.onopen = () => {
      traceSocket.send(JSON.stringify({
        token: getToken() || '',
        host: traceForm.host.trim(),
        max_hops: Number(traceForm.max_hops),
        timeout: Number(traceForm.timeout),
      }))
    }
    traceSocket.onmessage = (event) => {
      let message
      try { message = JSON.parse(event.data) } catch { return }
      if (message.type === 'start') {
        traceLiveOutput.value = `正在追踪 ${message.host} ...\n`
        return
      }
      if (message.type === 'install') {
        traceInstall.value = {
          status: message.status || 'running',
          progress: Number(message.progress || 0),
          message: message.message || '',
          stage: message.stage || '',
        }
        if (message.status === 'success') ElMessage.success('traceroute 安装完成，正在重新开始追踪')
        return
      }
      if (message.type === 'line') {
        traceLiveOutput.value += `${message.line}\n`
        if (message.hop) {
          const existing = traceLiveHops.value.find((item) => item.hop === message.hop.hop)
          if (existing) existing.ip = message.hop.ip || existing.ip
          else traceLiveHops.value.push({ ...message.hop })
          traceLiveHops.value.sort((a, b) => a.hop - b.hop)
        }
        nextTick(() => {
          const el = traceOutputRef.value
          if (el) el.scrollTop = el.scrollHeight
        })
        return
      }
      if (message.type === 'done') {
        traceFinished = true
        traceResult.value = message
        if (!traceLiveOutput.value) traceLiveOutput.value = message.output || ''
        traceLoading.value = false
        closeTraceSocket()
        ElMessage.success(`路由追踪完成，共 ${message.hops?.length || 0} 跳`)
        return
      }
      if (message.type === 'error') {
        traceFinished = true
        traceError.value = message.message || '路由追踪失败'
        traceLoading.value = false
        closeTraceSocket()
        ElMessage.error(traceError.value)
      }
    }
    traceSocket.onerror = () => {
      if (traceFinished) return
      traceError.value = '实时追踪连接失败，请确认后端 WebSocket 可用'
      traceLoading.value = false
    }
    traceSocket.onclose = () => {
      traceSocket = null
      if (!traceFinished && traceLoading.value) {
        traceLoading.value = false
        traceError.value = '实时追踪连接已断开'
      }
    }
  } catch (error) {
    traceLoading.value = false
    traceError.value = errorMessage(error)
    ElMessage.error(traceError.value)
  }
}

function ipToLong(ip) {
  return ip.split('.').reduce((acc, value) => ((acc << 8) + Number(value)) >>> 0, 0)
}

function longToIp(value) {
  return [24, 16, 8, 0].map((shift) => (value >>> shift) & 255).join('.')
}

function calculateSubnet(ip, prefix) {
  const prefixValue = Math.max(0, Math.min(32, Number(prefix) || 0))
  const parts = String(ip || '').trim().split('.')
  if (parts.length !== 4 || parts.some((part) => !/^\d+$/.test(part) || Number(part) > 255)) {
    return { error: '请输入合法的 IPv4 地址，例如 192.168.1.10' }
  }
  const mask = prefixValue === 0 ? 0 : (0xffffffff << (32 - prefixValue)) >>> 0
  const ipValue = ipToLong(parts.join('.'))
  const network = (ipValue & mask) >>> 0
  const broadcast = (network | (~mask >>> 0)) >>> 0
  const totalHosts = prefixValue >= 31 ? 0 : (2 ** (32 - prefixValue)) - 2
  const wildcard = (~mask) >>> 0
  const binary = parts.map((part) => Number(part).toString(2).padStart(8, '0')).join('.')
  return {
    cidr: `${longToIp(network)}/${prefixValue}`,
    mask: longToIp(mask),
    wildcard: longToIp(wildcard),
    network: longToIp(network),
    broadcast: longToIp(broadcast),
    range: prefixValue >= 31 ? `${longToIp(network)} - ${longToIp(broadcast)}` : `${longToIp(network + 1)} - ${longToIp(broadcast - 1)}`,
    hosts: totalHosts,
    binary,
    isPrivate: /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(longToIp(network)),
  }
}

// ==================== IPv6 子网计算 ====================
const IPV6_MAX = (1n << 128n) - 1n

function ipv6InPrefix(value, base, prefix) {
  if (prefix <= 0) return true
  const shift = 128n - BigInt(prefix)
  return (value >> shift) === (base >> shift)
}

function parseIpv6(value) {
  let text = String(value || '').trim().replace(/^\[|\]$/g, '')
  text = text.split('%')[0]
  if (!text) return null
  // 支持 ::ffff:192.168.1.1 这类内嵌 IPv4 写法
  const lastColon = text.lastIndexOf(':')
  const tail = text.slice(lastColon + 1)
  if (tail.includes('.')) {
    const v4 = tail.split('.')
    if (v4.length !== 4 || v4.some((part) => !/^\d+$/.test(part) || Number(part) > 255)) return null
    const high = ((Number(v4[0]) << 8) | Number(v4[1])).toString(16)
    const low = ((Number(v4[2]) << 8) | Number(v4[3])).toString(16)
    text = `${text.slice(0, lastColon + 1)}${high}:${low}`
  }
  const parts = text.split('::')
  if (parts.length > 2) return null
  let groups
  if (parts.length === 1) {
    groups = parts[0] ? parts[0].split(':') : []
    if (groups.length !== 8) return null
  } else {
    const left = parts[0] ? parts[0].split(':') : []
    const right = parts[1] ? parts[1].split(':') : []
    if (left.length + right.length >= 8) return null
    groups = [
      ...left,
      ...Array(8 - left.length - right.length).fill('0'),
      ...right,
    ]
  }
  if (groups.some((part) => !/^[0-9a-fA-F]{1,4}$/.test(part))) return null
  let parsed = 0n
  for (const group of groups) parsed = (parsed << 16n) | BigInt(parseInt(group, 16))
  return { value: parsed, groups: groups.map((group) => group.toLowerCase()) }
}

function ipv6Groups(value) {
  const groups = []
  let rest = value
  for (let i = 0; i < 8; i += 1) {
    groups.unshift((rest & 0xffffn).toString(16))
    rest >>= 16n
  }
  return groups
}

function compressIpv6(value) {
  const groups = ipv6Groups(value)
  let bestStart = -1
  let bestLength = 0
  for (let i = 0; i < groups.length; i += 1) {
    if (groups[i] !== '0') continue
    let end = i
    while (end < groups.length && groups[end] === '0') end += 1
    if (end - i > bestLength) {
      bestLength = end - i
      bestStart = i
    }
    i = end - 1
  }
  if (bestLength < 2) return groups.join(':')
  const left = groups.slice(0, bestStart).join(':')
  const right = groups.slice(bestStart + bestLength).join(':')
  if (!left && !right) return '::'
  if (!left) return `::${right}`
  if (!right) return `${left}::`
  return `${left}::${right}`
}

function expandIpv6(value) {
  return ipv6Groups(value).map((group) => group.padStart(4, '0')).join(':')
}

function ipv6Scope(value) {
  if (value === 0n) return '未指定地址（::/128）'
  if (value === 1n) return '回环地址（::1/128）'
  if (ipv6InPrefix(value, 0xffffn << 32n, 96)) return 'IPv4 映射地址（::ffff:0:0/96）'
  if (ipv6InPrefix(value, 0x0064ff9bn << 96n, 96)) return 'NAT64 地址（64:ff9b::/96）'
  if (ipv6InPrefix(value, 0x20010db8n << 96n, 32)) return '文档示例地址（2001:db8::/32）'
  if (ipv6InPrefix(value, 0x2002n << 112n, 16)) return '6to4 地址（2002::/16）'
  if (ipv6InPrefix(value, 0x2000n << 112n, 3)) return '全球单播地址（2000::/3）'
  if (ipv6InPrefix(value, 0xfc00n << 112n, 7)) return '唯一本地地址 ULA（fc00::/7）'
  if (ipv6InPrefix(value, 0xfe80n << 112n, 10)) return '链路本地地址（fe80::/10）'
  if (ipv6InPrefix(value, 0xff00n << 112n, 8)) return '组播地址（ff00::/8）'
  return '保留 / 其他地址'
}

function formatIpv6Count(count, hostBits) {
  if (count <= 1n) return `${count}`
  const decimal = count.toLocaleString('en-US')
  return hostBits > 64 ? `2^${hostBits} ≈ ${decimal}` : `2^${hostBits} = ${decimal}`
}

function calculateSubnet6(ip, prefix) {
  const parsed = parseIpv6(ip)
  if (!parsed) {
    return { error: '请输入合法的 IPv6 地址，例如 2001:db8::1 或 ::ffff:192.168.1.1' }
  }
  const prefixValue = Math.max(0, Math.min(128, Number(prefix) || 0))
  const hostBits = 128 - prefixValue
  const mask = prefixValue === 0 ? 0n : (IPV6_MAX << BigInt(hostBits)) & IPV6_MAX
  const network = parsed.value & mask
  const last = network | (IPV6_MAX ^ mask)
  const total = 1n << BigInt(hostBits)
  const usable = total > 1n ? total - 1n : 0n
  const binary = network.toString(2).padStart(128, '0').match(/.{16}/g).join(':')
  return {
    cidr: `${compressIpv6(network)}/${prefixValue}`,
    compressed: compressIpv6(parsed.value),
    expanded: expandIpv6(parsed.value),
    mask: compressIpv6(mask),
    network: compressIpv6(network),
    last: compressIpv6(last),
    totalText: formatIpv6Count(total, hostBits),
    usableText: formatIpv6Count(usable, hostBits),
    scopeLabel: ipv6Scope(network),
    binary,
  }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text || '')
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择文本')
  }
}

function initTerminal() {
  if (!terminalRef.value || terminal) return
  terminal = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: 'Consolas, "Cascadia Mono", monospace',
    theme: { background: '#07111f', foreground: '#c7e4f5', cursor: '#38bdf8', selectionBackground: '#164e63' },
    scrollback: 3000,
  })
  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalRef.value)
  terminal.writeln('\x1b[36m系统工具 · SSH 远程终端\x1b[0m')
  terminal.writeln('填写连接配置后点击「连接」。\x1b[90m// 仅限已授权的运维操作\x1b[0m')
  fitAddon.fit()
  terminalReady.value = true
  resizeObserver = new ResizeObserver(() => fitAddon?.fit())
  resizeObserver.observe(terminalRef.value)
  terminal.onData((data) => {
    if (sshConnected.value && socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'input', data }))
    }
  })
  terminal.onResize(({ cols, rows }) => {
    if (socket?.readyState === WebSocket.OPEN && sshConnected.value) {
      socket.send(JSON.stringify({ type: 'resize', cols, rows }))
    }
  })
}

async function loadNotes(selectFirst = false) {
  notesLoading.value = true
  try {
    const { data } = await notesApi.list()
    notes.value = data.items || []
    sharedNotes.value = data.shared || []
    if (selectedNote.value) {
      const all = [...notes.value, ...sharedNotes.value]
      selectedNote.value = all.find((note) => note.id === selectedNote.value.id) || null
      if (!selectedNote.value) noteFormActive.value = false
    }
    if (selectFirst && !selectedNote.value && notes.value.length) {
      selectNote(notes.value[0], false)
    }
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    notesLoading.value = false
  }
}

function resetNoteForm() {
  noteForm.title = ''
  noteForm.content = ''
  noteForm.note_format = 'markdown'
  notePreview.value = false
}

function newNote() {
  notesTab.value = 'mine'
  selectedNote.value = null
  selectedNoteIds.value = []
  resetNoteForm()
  noteFormActive.value = true
  notePreview.value = false
}

function selectNote(note, isShared = false) {
  selectedNote.value = note
  notesTab.value = isShared ? 'shared' : 'mine'
  noteForm.title = note.title || ''
  noteForm.content = note.content || ''
  noteForm.note_format = note.note_format || 'markdown'
  notePreview.value = false
  noteFormActive.value = true
}

function onNotesTabChange() {
  selectedNote.value = null
  selectedNoteIds.value = []
  noteFormActive.value = false
  resetNoteForm()
}

function toggleSelectNote(id) {
  const index = selectedNoteIds.value.indexOf(id)
  if (index >= 0) selectedNoteIds.value.splice(index, 1)
  else selectedNoteIds.value.push(id)
}

function toggleSelectAllNotes(checked) {
  selectedNoteIds.value = checked ? filteredNotes.value.map((note) => note.id) : []
}

async function saveNote() {
  if (!noteForm.title.trim()) {
    ElMessage.warning('请填写笔记标题')
    return
  }
  if (selectedNote.value && !selectedNote.value.is_owner) {
    ElMessage.warning('共享笔记为只读，请先保存副本')
    return
  }
  noteSaving.value = true
  try {
    const payload = {
      title: noteForm.title.trim(),
      content: noteForm.content,
      note_format: noteForm.note_format,
    }
    let note
    if (selectedNote.value) {
      const { data } = await notesApi.update(selectedNote.value.id, payload)
      note = data
      ElMessage.success('笔记已更新')
    } else {
      const { data } = await notesApi.create(payload)
      note = data
      ElMessage.success('笔记已创建')
    }
    selectedNote.value = note
    await loadNotes()
    selectNote(note, false)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    noteSaving.value = false
  }
}

async function deleteCurrentNote() {
  if (!selectedNote.value || !selectedNote.value.is_owner) return
  try {
    await ElMessageBox.confirm(
      `确定删除《${selectedNote.value.title}》吗？\n删除后将永久移除，所有已分享用户会立即失去访问权限，且无法恢复。`,
      '确认删除笔记',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await notesApi.remove(selectedNote.value.id)
    ElMessage.success('笔记已删除')
    selectedNote.value = null
    noteFormActive.value = false
    selectedNoteIds.value = []
    await loadNotes()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function batchDeleteNotes() {
  if (!selectedNoteIds.value.length) return
  const count = selectedNoteIds.value.length
  try {
    await ElMessageBox.confirm(
      `即将永久删除 ${count} 条个人笔记，并解除其全部分享关系。\n此操作不可恢复，已分享用户将立即无法访问这些笔记。`,
      `批量删除 ${count} 条笔记`,
      { type: 'warning', confirmButtonText: `确认删除 ${count} 条`, cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const { data } = await notesApi.batchDelete(selectedNoteIds.value)
    ElMessage.success(`已删除 ${data.deleted} 条笔记`)
    selectedNoteIds.value = []
    selectedNote.value = null
    noteFormActive.value = false
    await loadNotes()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function batchShareNotes() {
  if (!selectedNoteIds.value.length) return
  await openShareDialog(selectedNoteIds.value)
}

async function openShareDialog(noteIds) {
  if (!noteIds?.length) return
  shareTargetIds.value = [...noteIds]
  const first = notes.value.find((note) => note.id === noteIds[0])
  shareUserIds.value = noteIds.length === 1 && first?.shared_to
    ? first.shared_to.map((user) => user.id)
    : []
  try {
    const { data } = await notesApi.users()
    shareUsers.value = data || []
  } catch (error) {
    shareUsers.value = []
    ElMessage.error(errorMessage(error))
    return
  }
  shareVisible.value = true
}

async function confirmShare() {
  const count = shareTargetIds.value.length
  const userCount = shareUserIds.value.length
  const users = shareUserIds.value.length
    ? shareUsers.value.filter((user) => shareUserIds.value.includes(user.id)).map((user) => user.real_name || user.username).join('、')
    : '无（取消全部分享）'
  try {
    await ElMessageBox.confirm(
      `将分享 ${count} 条笔记给：${users}。\n被分享人只能查看和保存副本，不能修改或删除原笔记；保存后会覆盖这些笔记原有的分享名单。
${userCount ? '对方将立即获得访问权限。' : '对方将立即失去访问权限。'}`,
      count > 1 ? `确认批量分享 ${count} 条笔记` : '确认分享笔记',
      { type: 'warning', confirmButtonText: '确认分享', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  shareSaving.value = true
  try {
    if (count > 1 || shareTargetIds.value.length > 1) {
      await notesApi.batchShare(shareTargetIds.value, shareUserIds.value)
    } else {
      await notesApi.share(shareTargetIds.value[0], shareUserIds.value)
    }
    ElMessage.success('分享设置已保存')
    shareVisible.value = false
    selectedNoteIds.value = []
    await loadNotes()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    shareSaving.value = false
  }
}

async function saveSharedNote(note) {
  try {
    await ElMessageBox.confirm(
      `将从《${note.title}》创建一份归你所有的副本。\n原笔记不会改变，副本不会自动与原作者同步，也不会继承原分享关系。`,
      '保存到我的笔记',
      { type: 'info', confirmButtonText: '保存副本', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const { data } = await notesApi.copy(note.id)
    ElMessage.success('已保存副本到「我的笔记」')
    notesTab.value = 'mine'
    await loadNotes()
    selectNote(data, false)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function formatNoteTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function escapeNoteHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderInlineMarkdown(value) {
  return value
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}

function renderMarkdown(value) {
  const lines = escapeNoteHtml(value || '').split('\n')
  const output = []
  let inCode = false
  let inList = false
  const closeList = () => {
    if (inList) {
      output.push('</ul>')
      inList = false
    }
  }
  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      closeList()
      output.push(inCode ? '</code></pre>' : '<pre><code>')
      inCode = !inCode
      continue
    }
    if (inCode) {
      output.push(`${line}\n`)
      continue
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    const item = line.match(/^\s*[-*]\s+(.+)$/)
    if (heading) {
      closeList()
      output.push(`<h${heading[1].length + 1}>${renderInlineMarkdown(heading[2])}</h${heading[1].length + 1}>`)
    } else if (item) {
      if (!inList) {
        output.push('<ul>')
        inList = true
      }
      output.push(`<li>${renderInlineMarkdown(item[1])}</li>`)
    } else if (!line.trim()) {
      closeList()
      output.push('<p class="md-empty">&nbsp;</p>')
    } else {
      closeList()
      output.push(`<p>${renderInlineMarkdown(line)}</p>`)
    }
  }
  closeList()
  if (inCode) output.push('</code></pre>')
  return output.join('')
}

async function loadCaptureInterfaces() {
  captureInterfacesLoading.value = true
  captureError.value = ''
  try {
    const { data } = await toolsApi.captureInterfaces()
    captureCapability.value = data
    captureInterfaces.value = data.interfaces || []
    if (!captureInterface.value && captureInterfaces.value.length) {
      const preferred = captureInterfaces.value.find((item) => item.ips?.length) || captureInterfaces.value[0]
      captureInterface.value = preferred.id
    }
  } catch (error) {
    captureCapability.value = { available: false, message: errorMessage(error) }
    captureError.value = errorMessage(error)
    captureInterfaces.value = []
  } finally {
    captureInterfacesLoading.value = false
  }
}

function stopCapturePolling() {
  if (capturePollTimer) {
    clearInterval(capturePollTimer)
    capturePollTimer = null
  }
}

async function refreshCaptureStatus() {
  if (!captureJob.value?.id) return
  try {
    const { data } = await toolsApi.captureStatus(captureJob.value.id)
    captureJob.value = data
    if (!['starting', 'running', 'stopping'].includes(data.status)) {
      stopCapturePolling()
      await loadCaptureRecords()
      // 报告由抓包线程保存，完成状态与写盘可能相差几百毫秒
      setTimeout(loadCaptureRecords, 800)
    }
  } catch (error) {
    captureError.value = errorMessage(error)
    stopCapturePolling()
  }
}

async function loadCaptureRecords() {
  captureRecordsLoading.value = true
  try {
    const { data } = await toolsApi.captureRecords()
    captureRecords.value = data.items || []
    captureRecordSelection.value = []
  } catch (error) {
    captureError.value = errorMessage(error)
  } finally {
    captureRecordsLoading.value = false
  }
}

function onCaptureRecordSelection(rows) {
  captureRecordSelection.value = rows
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function downloadCaptureRecord(row) {
  try {
    const response = await toolsApi.captureRecordDownload(row.id)
    saveBlob(response.data, row.filename)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function saveSelectedCaptureRecords() {
  const ids = captureRecordSelection.value.map((item) => item.id)
  if (!ids.length) {
    ElMessage.warning('请先勾选要保存的抓包记录')
    return
  }
  try {
    const response = await toolsApi.captureRecordsBatchDownload(ids)
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    saveBlob(response.data, `capture-reports-${stamp}.zip`)
    ElMessage.success(`已保存 ${ids.length} 个 .cap 抓包文件`)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function deleteCaptureRecord(row) {
  try {
    await ElMessageBox.confirm(`确定删除抓包文件「${row.filename}」及其 JSON 分析报告？`, '删除抓包文件', { type: 'warning' })
    await toolsApi.captureRecordsBatchDelete([row.id])
    ElMessage.success('抓包记录已删除')
    await loadCaptureRecords()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

async function deleteSelectedCaptureRecords() {
  const ids = captureRecordSelection.value.map((item) => item.id)
  if (!ids.length) {
    ElMessage.warning('请先勾选要删除的抓包记录')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 条抓包文件及其 JSON 分析报告？删除后不可恢复。`, '批量删除抓包文件', { type: 'warning' })
    await toolsApi.captureRecordsBatchDelete(ids)
    ElMessage.success(`已删除 ${ids.length} 条抓包记录`)
    await loadCaptureRecords()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function startCapturePolling() {
  stopCapturePolling()
  capturePollTimer = setInterval(refreshCaptureStatus, 1000)
}

async function startCapture() {
  if (!captureInterface.value) {
    ElMessage.warning('请选择抓包网卡')
    return
  }
  captureStarting.value = true
  captureError.value = ''
  try {
    const found = captureInterfaces.value.find((item) => item.id === captureInterface.value)
    const { data } = await toolsApi.captureStart({
      interface: captureInterface.value,
      interface_label: found?.label || found?.name || captureInterface.value,
      duration: Number(captureDuration.value),
      max_packets: Number(captureMaxPackets.value),
      bpf_filter: captureFilter.value.trim(),
    })
    captureJob.value = data
    if (data.status === 'error') captureError.value = data.error || '抓包启动失败'
    else startCapturePolling()
  } catch (error) {
    captureError.value = errorMessage(error)
    ElMessage.error(captureError.value)
  } finally {
    captureStarting.value = false
  }
}

async function stopCapture() {
  if (!captureJob.value?.id) return
  captureStarting.value = true
  try {
    const { data } = await toolsApi.captureStop(captureJob.value.id)
    captureJob.value = data
    if (['starting', 'running', 'stopping'].includes(data.status)) {
      startCapturePolling()
      ElMessage.info('正在停止并保存抓包文件...')
      return
    }
    stopCapturePolling()
    await loadCaptureRecords()
    setTimeout(loadCaptureRecords, 500)
    if (data.status === 'error' || data.save_error) {
      captureError.value = data.save_error || data.error || '抓包文件保存失败'
      ElMessage.error(captureError.value)
    } else {
      ElMessage.success(data.record_id ? '抓包已停止，.cap 文件已保存到记录' : '抓包已停止')
    }
  } catch (error) {
    captureError.value = errorMessage(error)
    ElMessage.error(captureError.value)
  } finally {
    captureStarting.value = false
  }
}

function captureSeverityText(severity) {
  return { critical: '高危', warning: '警告', info: '提示' }[severity] || '提示'
}

function captureSeverityType(severity) {
  return { critical: 'danger', warning: 'warning', info: 'info' }[severity] || 'info'
}

async function loadPublicIp(force = false) {
  publicIpLoading.value = true
  publicIpError.value = ''
  try {
    const res = await toolsApi.publicIp(force)
    publicIpResult.value = res.data
  } catch (error) {
    publicIpError.value = error?.response?.data?.detail || error?.message || '公网 IP 查询失败'
  } finally {
    publicIpLoading.value = false
  }
}

async function onTabChange(name) {
  if (name !== 'tracert' && traceLoading.value) stopTracert()
  if (name === 'publicip' && !publicIpResult.value && !publicIpLoading.value) await loadPublicIp(false)
  if (name === 'capture') {
    await loadCaptureInterfaces()
    await loadCaptureRecords()
    if (captureJob.value?.id && captureRunning.value) startCapturePolling()
  } else {
    stopCapturePolling()
  }
  if (name === 'notes') {
    await loadNotes(true)
  }
  if (name === 'ssh') {
    await nextTick()
    initTerminal()
    setTimeout(() => fitAddon?.fit(), 80)
  }
}

function setStatus(text, cls) {
  sshStatusText.value = text
  sshStatusClass.value = cls
}

function connectSsh() {
  if (!sshForm.host.trim()) { ElMessage.warning('请输入 SSH 主机'); return }
  if (!sshForm.username.trim()) { ElMessage.warning('请输入 SSH 用户名'); return }
  if (sshForm.authType === 'password' && !sshForm.password) {
    ElMessage.warning('请输入 SSH 密码，或切换为私钥认证')
    return
  }
  if (!terminal) initTerminal()
  if (!terminal) return
  disconnectSsh(false)
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/api/tools/ssh`
  sshConnecting.value = true
  setStatus('正在连接...', 'connecting')
  terminal.writeln(`\r\n\x1b[36m$ ssh ${sshForm.username}@${sshForm.host}:${sshForm.port}\x1b[0m`)
  socket = new WebSocket(url)
  socket.onopen = () => {
    const { host, port, username, password, privateKey, passphrase, acceptNewHostKey } = sshForm
    socket.send(JSON.stringify({
      token: getToken() || '',
      host, port, username, password,
      private_key: sshForm.authType === 'key' ? privateKey : '',
      passphrase: sshForm.authType === 'password' ? '' : passphrase,
      accept_new_host_key: acceptNewHostKey,
      cols: terminal.cols,
      rows: terminal.rows,
    }))
  }
  socket.onmessage = (event) => {
    let message = null
    try { message = JSON.parse(event.data) } catch { message = null }
    if (!message) { terminal.write(event.data); return }
    if (message.type === 'data') { terminal.write(message.data); return }
    if (message.type === 'ready') {
      sshConnecting.value = false
      sshConnected.value = true
      setStatus('已连接', 'connected')
      terminal.focus()
      fitAddon?.fit()
      socket.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }))
      return
    }
    if (message.type === 'error') {
      sshConnecting.value = false
      setStatus('连接失败', 'error')
      terminal.writeln(`\r\n\x1b[31m${message.message || 'SSH 连接失败'}\x1b[0m`)
      ElMessage.error(message.message || 'SSH 连接失败')
    }
  }
  socket.onerror = () => {
    sshConnecting.value = false
    setStatus('连接错误', 'error')
    terminal.writeln('\r\n\x1b[31mWebSocket 连接失败，请检查服务状态\x1b[0m')
  }
  socket.onclose = (event) => {
    sshConnecting.value = false
    sshConnected.value = false
    if (sshStatusText.value !== '连接失败') setStatus('连接已断开', 'idle')
    if (event.code !== 1000 && event.code !== 1001) {
      terminal.writeln(`\r\n\x1b[33m连接已关闭（${event.code}）\x1b[0m`)
    }
    socket = null
  }
}

function disconnectSsh(notify = true) {
  if (socket) {
    try {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'disconnect' }))
      socket.close(1000)
    } catch { /* 忽略 */ }
    socket = null
  }
  sshConnected.value = false
  sshConnecting.value = false
  if (notify) setStatus('连接已断开', 'idle')
}

function setSftpStatus(text, cls = 'idle') {
  sftpStatusText.value = text
  sftpStatusClass.value = cls
}

function sftpCredentials() {
  return {
    host: sshForm.host.trim(),
    port: sshForm.port,
    username: sshForm.username.trim(),
    password: sshForm.password,
    private_key: sshForm.authType === 'key' ? sshForm.privateKey : '',
    passphrase: sshForm.authType === 'key' ? sshForm.passphrase : '',
    accept_new_host_key: sshForm.acceptNewHostKey,
  }
}

function normalizeSftpPath(value) {
  let path = String(value || '/').trim()
  if (!path.startsWith('/')) path = `/${path}`
  path = path.replace(/\/+/g, '/').replace(/\/$/, '')
  return path || '/'
}

function joinSftpPath(base, name) {
  return `${normalizeSftpPath(base).replace(/\/$/, '')}/${name}`.replace(/\/+/g, '/')
}

function sftpRowClass({ row }) {
  return row?.is_dir ? 'sftp-dir-row' : ''
}

async function enterSftpDirectory(row) {
  if (!row?.is_dir) return
  sftpDir.value = joinSftpPath(sftpDir.value, row.name)
  await loadSftpList()
}

async function goSftpParent() {
  const current = normalizeSftpPath(sftpDir.value)
  if (current === '/') return
  const index = current.lastIndexOf('/')
  sftpDir.value = index <= 0 ? '/' : current.slice(0, index)
  await loadSftpList()
}

async function onSftpRowClick(row) {
  if (row?.is_dir) await enterSftpDirectory(row)
}

function validateSftpConnection() {
  if (!sshForm.host.trim() || !sshForm.username.trim()) {
    ElMessage.warning('请先填写主机和 SSH 用户名')
    return false
  }
  if (sshForm.authType === 'password' && !sshForm.password) {
    ElMessage.warning('请输入密码，或切换为私钥认证')
    return false
  }
  return true
}

async function loadSftpList() {
  if (!validateSftpConnection()) return
  sftpDir.value = normalizeSftpPath(sftpDir.value)
  sftpListLoading.value = true
  setSftpStatus('正在读取目录...', 'connecting')
  try {
    const { data } = await toolsApi.sftpList({ ...sftpCredentials(), path: sftpDir.value })
    sftpFiles.value = data.items || []
    setSftpStatus(`已连接 · ${sftpFiles.value.length} 个条目`, 'connected')
  } catch (error) {
    sftpFiles.value = []
    setSftpStatus('读取失败', 'error')
    ElMessage.error(errorMessage(error))
  } finally {
    sftpListLoading.value = false
  }
}

function pickSftpFile() {
  sftpFileRef.value?.click()
}

function onSftpFileChange(event) {
  const file = event.target.files?.[0]
  sftpFile.value = file || null
  event.target.value = ''
  sftpUploadPercent.value = 0
}

function onSftpDrop(event) {
  sftpDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) {
    sftpFile.value = file
    sftpUploadPercent.value = 0
  }
}

function clearSftpFile() {
  sftpFile.value = null
  sftpUploadPercent.value = 0
}

async function uploadSftpFile() {
  if (!sftpFile.value) return
  if (!validateSftpConnection()) return
  if (sftpFile.value.size > 200 * 1024 * 1024) {
    ElMessage.warning('单个文件不能超过 200MB')
    return
  }
  sftpUploading.value = true
  sftpUploadPercent.value = 0
  setSftpStatus('正在上传...', 'connecting')
  try {
    const formData = new FormData()
    formData.append('file', sftpFile.value)
    const credentials = sftpCredentials()
    Object.entries(credentials).forEach(([key, value]) => {
      formData.append(key, value === null || value === undefined ? '' : String(value))
    })
    formData.append('remote_dir', normalizeSftpPath(sftpDir.value))
    const { data } = await toolsApi.sftpUpload(formData, (event) => {
      if (event.total) sftpUploadPercent.value = Math.round((event.loaded / event.total) * 100)
    })
    sftpUploadPercent.value = 100
    setSftpStatus(`已上传 ${data.name}`, 'connected')
    ElMessage.success(`文件已上传到 ${data.remote_path}`)
    sftpFile.value = null
    await loadSftpList()
  } catch (error) {
    setSftpStatus('上传失败', 'error')
    ElMessage.error(errorMessage(error))
  } finally {
    sftpUploading.value = false
  }
}

async function downloadSftpFile(file) {
  if (!validateSftpConnection()) return
  try {
    setSftpStatus(`正在下载 ${file.name}...`, 'connecting')
    const response = await toolsApi.sftpDownload({ ...sftpCredentials(), path: joinSftpPath(sftpDir.value, file.name) })
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = file.name
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    setSftpStatus(`已下载 ${file.name}`, 'connected')
  } catch (error) {
    setSftpStatus('下载失败', 'error')
    ElMessage.error(errorMessage(error))
  }
}

function formatSize(size) {
  const value = Number(size || 0)
  if (value >= 1024 * 1024 * 1024) return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}

function formatSftpTime(value) {
  if (!value) return '-'
  return new Date(Number(value) * 1000).toLocaleString('zh-CN', { hour12: false })
}

function clearTerminal() {
  terminal?.clear()
  terminal?.write('\x1b[36m系统工具 · SSH 远程终端\x1b[0m\r\n')
}

onBeforeUnmount(() => {
  stopCapturePolling()
  closeTraceSocket()
  disconnectSsh(false)
  resizeObserver?.disconnect()
  terminal?.dispose()
  terminal = null
})
</script>

<style scoped>
.tools-view { padding: 4px 0; }
.tools-card { border-radius: 12px; }
.tools-header { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.public-ip-layout { display: flex; flex-direction: column; gap: 12px; }
.public-ip-card { padding: 16px; border: 1px solid #e3eef7; border-radius: 10px; background: #fbfdff; }
.public-ip-card-head { display: flex; align-items: center; justify-content: space-between; color: #6f8598; font-size: 12px; }
.public-ip-main { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 12px 0; }
.public-ip-value { color: #0f6fae; font-size: 28px; font-weight: 700; letter-spacing: .5px; font-family: Consolas, monospace; }
.public-ip-tags { display: flex; gap: 6px; }
.public-ip-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 20px; padding: 10px 0; border-top: 1px dashed #dbe8f2; }
.public-ip-grid div { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; min-width: 0; }
.public-ip-grid span { color: #8b9bab; font-size: 11px; }
.public-ip-grid b { color: #33495b; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.public-ip-note { margin: 8px 0 0; color: #95a6b5; font-size: 10px; }
.tools-title { display: flex; align-items: center; gap: 8px; color: #1f2d3d; font-size: 17px; font-weight: 600; }
.tools-title .el-icon { color: #0ea5e9; }
.tools-sub { margin-top: 5px; color: #8a99a8; font-size: 12px; }
.tab-title { display: inline-flex; align-items: center; gap: 6px; }
.tool-intro { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 15px; border: 1px solid #e3eef7; border-radius: 9px; background: linear-gradient(90deg, #f4faff, #fbfdff); }
.tool-intro strong { color: #24425b; font-size: 13px; }
.tool-intro p { margin: 4px 0 0; color: #8598a9; font-size: 11px; }
.quick-oids { display: flex; align-items: center; flex-wrap: wrap; gap: 3px; color: #9aa9b8; font-size: 10px; }
.quick-oids .el-button { font-size: 11px; }
.tool-form { margin-top: 14px; }
.tool-grid { display: grid; grid-template-columns: minmax(180px, 1.5fr) repeat(3, minmax(110px, 0.6fr)); gap: 0 14px; }
.tool-grid.wide { grid-template-columns: minmax(190px, 1.2fr) minmax(190px, 1.2fr) repeat(5, minmax(88px, 0.55fr)); }
.tool-grid :deep(.el-form-item) { margin-bottom: 14px; }
.tool-actions { display: flex; gap: 8px; padding-top: 4px; }
.trace-live-panel { margin-top: 10px; }
.trace-install-panel { margin-top: 12px; padding: 12px 14px; border: 1px solid #dbeafe; border-radius: 8px; background: #f8fbff; }
.trace-install-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 8px; color: #245b80; font-size: 12px; font-weight: 600; }
.trace-install-head b { color: #1677b8; font-family: Consolas, monospace; }
.trace-install-message { margin-top: 7px; color: #70899b; font-size: 11px; overflow-wrap: anywhere; }
.trace-live-dot { display: inline-block; width: 7px; height: 7px; margin-right: 7px; border-radius: 50%; background: #10b981; box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15); animation: trace-pulse 1.2s ease-in-out infinite; }
@keyframes trace-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.45; transform: scale(0.8); } }
.trace-hop-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.trace-hop { display: flex; align-items: center; gap: 7px; padding: 5px 9px; border: 1px solid #dbeaf3; border-radius: 6px; background: #fbfdff; }
.trace-hop span { color: #8ba1b1; font-size: 9px; }
.trace-hop b { color: #24617f; font-family: Consolas, monospace; font-size: 10px; }
.trace-waiting { margin-top: 10px; padding: 16px; border: 1px dashed #d5e6f0; border-radius: 8px; color: #8da4b4; font-size: 11px; text-align: center; }
.result-strip { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; border-radius: 8px; background: #f7fbfd; color: #7f95a6; font-size: 11px; }
.result-strip b { color: #0f6f95; font-family: Consolas, monospace; }
.result-strip .warn { color: #b45309; }
.snmp-category-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.snmp-category-bar :deep(.el-button + .el-button) { margin-left: 0; }
.snmp-result-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; color: #7f95a6; font-size: 11px; }
.snmp-result-toolbar b { color: #0f6f95; font-family: Consolas, monospace; }
.snmp-result-table { margin-top: 8px; }
.snmp-raw-collapse { margin-top: 8px; }
.snmp-raw-collapse :deep(.el-collapse-item__header) { height: 34px; color: #7f95a6; font-size: 11px; }
.tool-output { margin-top: 10px; max-height: 360px; overflow: auto; padding: 13px 15px; border: 1px solid #dbeaf3; border-radius: 8px; background: #07111f; color: #c7e4f5; font-family: Consolas, 'Cascadia Mono', monospace; font-size: 12px; line-height: 1.7; white-space: pre-wrap; }
.ping-summary { display: flex; gap: 9px; margin-top: 14px; }
.ping-summary > div { flex: 1; padding: 9px 12px; border: 1px solid #e6eef5; border-radius: 8px; background: #fbfdff; }
.ping-summary span { display: block; color: #97a8b8; font-size: 10px; }
.ping-summary b { display: block; margin-top: 3px; color: #2b4b62; font-family: Consolas, monospace; font-size: 15px; }
.ping-summary .ok b { color: #059669; }
.ping-summary .bad b { color: #dc2626; }
.subnet-inputs { display: flex; align-items: center; gap: 10px; max-width: 640px; margin: 16px 0; }
.subnet-ip { flex: 1; }
.subnet-prefix { width: 120px; }
.slash { color: #94a3b8; font-size: 18px; }
.subnet-hint { color: #94a3b8; font-size: 10px; }
.subnet-mode { margin-bottom: 14px; }
.subnet-results { max-width: 880px; }
.subnet-big { display: flex; align-items: baseline; gap: 10px; padding: 14px 16px; border-radius: 9px; background: #07111f; color: #c7e4f5; }
.subnet-big span { color: #6a94ab; font-size: 11px; }
.subnet-big strong { color: #7dd3fc; font-family: Consolas, monospace; font-size: 24px; }
.subnet-big small { margin-left: auto; color: #10b981; font-size: 10px; }
.subnet-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px; }
.subnet-grid > div { padding: 9px 11px; border: 1px solid #e6eef5; border-radius: 8px; background: #fbfdff; }
.subnet-grid span { display: block; color: #97a8b8; font-size: 10px; }
.subnet-grid b { display: block; margin-top: 3px; color: #24425b; font-family: Consolas, monospace; font-size: 13px; }
.subnet-binary { margin-top: 10px; padding: 9px 11px; border: 1px dashed #cfe4f0; border-radius: 8px; }
.subnet-binary span { display: block; color: #97a8b8; font-size: 10px; }
.subnet-binary code { color: #0e7490; font-family: Consolas, monospace; font-size: 11px; }
.ssh-layout { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 16px; margin-top: 4px; align-items: stretch; }
.ssh-panel { padding: 16px; border: 1px solid #e4eef6; border-radius: 10px; background: #fbfdff; }
.ssh-panel-title { font-size: 13px; margin-bottom: 10px; color: #24425b; font-weight: 600; }
.ssh-inline { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 8px; }
.ssh-actions { display: flex; gap: 7px; margin-top: 2px; flex-wrap: wrap; }
.ssh-status { display: flex; align-items: center; gap: 6px; margin-top: 10px; font-size: 11px; color: #94a3b8; }
.ssh-status i { width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; }
.ssh-status.connecting { color: #d97706; } .ssh-status.connecting i { background: #f59e0b; }
.ssh-status.connected { color: #059669; } .ssh-status.connected i { background: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,.12); }
.ssh-status.error { color: #dc2626; } .ssh-status.error i { background: #ef4444; }
.ssh-form :deep(.el-form-item__label) { font-size: 12px; }
.ssh-actions .el-button, .sftp-actions .el-button, .tool-actions .el-button { min-height: 36px; font-size: 13px; }
.terminal-panel { min-width: 0; min-height: 0; overflow: hidden; border: 1px solid #1e3a4d; border-radius: 10px; background: #07111f; }
.terminal-bar { display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 11px; border-bottom: 1px solid #163247; background: #0b1d2e; }
.terminal-bar span { display: inline-flex; gap: 4px; }
.terminal-bar span i { width: 7px; height: 7px; border-radius: 50%; background: #ef4444; }
.terminal-bar span i:nth-child(2) { background: #f59e0b; } .terminal-bar span i:nth-child(3) { background: #10b981; }
.terminal-bar b { color: #7dd3fc; font-family: Consolas, monospace; font-size: 11px; font-weight: 400; }
.terminal-bar small { margin-left: auto; color: #46677c; font-family: Consolas, monospace; font-size: 9px; }
.terminal-host { height: clamp(360px, 57vh, 680px); padding: 6px; }
.terminal-host :deep(.xterm) { height: 100%; }

.sftp-layout {
  display: grid;
  grid-template-columns: 350px minmax(0, 1fr);
  gap: 16px;
  min-height: min(640px, calc(100vh - 300px));
}

.sftp-panel,
.sftp-upload-card,
.sftp-list-card {
  border: 1px solid #e4eef6;
  border-radius: 10px;
  background: #fbfdff;
}

.sftp-panel { padding: 15px; }
.sftp-panel-title { color: #24425b; font-size: 13px; font-weight: 600; }
.sftp-use-ssh { margin: 4px 0 12px; color: #91a4b4; font-size: 10px; }
.sftp-form :deep(.el-form-item) { margin-bottom: 12px; }
.sftp-form :deep(.el-form-item__label) { font-size: 12px; }
.sftp-load-btn { width: 100%; min-height: 36px; }
.sftp-main { display: flex; flex-direction: column; gap: 12px; min-width: 0; min-height: 0; }
.sftp-upload-card {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 15px;
  transition: border-color .18s ease, background .18s ease;
}
.sftp-upload-card.is-dragging { border-color: #38bdf8; background: #f0faff; }
.sftp-upload-icon {
  width: 42px; height: 42px; display: flex; align-items: center; justify-content: center;
  border-radius: 10px; color: #0ea5e9; background: #e0f2fe; font-size: 22px;
}
.sftp-upload-copy { flex: 1; min-width: 180px; }
.sftp-upload-copy strong { display: block; color: #24425b; font-size: 13px; }
.sftp-upload-copy small { display: block; margin-top: 3px; color: #90a3b2; font-size: 10px; }
.sftp-hidden-input { display: none; }
.sftp-progress { flex-basis: 100%; width: 100%; }
.sftp-list-card { flex: 1; min-height: 240px; padding: 0; overflow: hidden; }
.sftp-list-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 11px 14px; border-bottom: 1px solid #eef3f8; }
.sftp-list-head strong { color: #24425b; font-size: 13px; }
.sftp-list-head span { margin-left: 8px; color: #8da2b2; font-family: Consolas, monospace; font-size: 10px; }
.sftp-location { display: flex; align-items: baseline; flex-wrap: wrap; gap: 2px; min-width: 0; }
.sftp-location small { margin-left: 8px; color: #a4b5c2; font-size: 9px; }
.sftp-list-actions { display: flex; align-items: center; gap: 5px; flex-shrink: 0; }
.sftp-list-card :deep(.sftp-dir-row) { cursor: pointer; }
.sftp-list-card :deep(.sftp-dir-row:hover > td) { background: #f1faff !important; }
.sftp-enter-hint { margin-left: 5px; padding: 0 4px; border-radius: 3px; color: #0e7490; background: #e0f2fe; font-size: 9px; font-style: normal; }
.sftp-list-card :deep(.el-table) { font-size: 12px; }
.sftp-name { display: inline-flex; align-items: center; gap: 6px; color: #405c70; font-size: 12px; }
.sftp-name.folder { color: #b7791f; }

.notes-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  min-height: min(620px, calc(100vh - 300px));
}

.notes-side,
.notes-editor {
  border: 1px solid #e4eef6;
  border-radius: 10px;
  background: #fbfdff;
  min-height: 0;
}

.notes-side { display: flex; flex-direction: column; padding: 13px; overflow: hidden; }
.notes-side-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.notes-side-head strong { display: block; color: #24425b; font-size: 14px; }
.notes-side-head span { color: #91a4b4; font-size: 10px; }
.notes-tabs { margin: 10px 0 8px; width: 100%; }
.notes-tabs :deep(.el-radio-button) { flex: 1; }
.notes-tabs :deep(.el-radio-button__inner) { width: 100%; padding: 7px 8px; font-size: 11px; }
.notes-search { margin-bottom: 8px; }
.notes-batch-bar {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  min-height: 29px; padding: 2px 4px; margin-bottom: 4px;
  border-bottom: 1px solid #edf4f9;
}
.notes-batch-bar :deep(.el-checkbox__label) { color: #70879a; font-size: 11px; }
.notes-batch-bar .el-button { font-size: 10px; }
.notes-list { flex: 1; min-height: 0; overflow: auto; padding-right: 2px; }
.note-item {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 10px 8px; margin-bottom: 5px;
  border: 1px solid transparent; border-radius: 8px;
  background: #f7fbfe; cursor: pointer; transition: all .16s ease;
}
.note-item:hover { border-color: #cfe8f6; background: #f2faff; }
.note-item.active { border-color: #7dd3fc; background: #eaf8ff; box-shadow: 0 2px 8px rgba(14,165,233,.08); }
.note-item.shared-note { align-items: center; gap: 5px; }
.note-check { flex-shrink: 0; margin-top: 1px; }
.note-check :deep(.el-checkbox__label) { display: none; }
.note-item-main { flex: 1; min-width: 0; }
.note-item-title { display: flex; align-items: center; gap: 6px; color: #2d4a60; font-size: 12px; font-weight: 600; }
.note-item-title span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.note-item-title em {
  flex-shrink: 0; padding: 1px 4px; border-radius: 3px;
  color: #0e7490; background: #dff7ff; font-size: 8px; font-style: normal;
}
.note-item-meta { display: flex; gap: 8px; margin-top: 4px; color: #94a3b8; font-size: 9px; }
.notes-editor { display: flex; flex-direction: column; padding: 14px 16px; overflow: hidden; }
.notes-editor-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.notes-editor-title { display: flex; align-items: center; gap: 7px; color: #24425b; font-size: 14px; font-weight: 600; }
.notes-editor-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.notes-editor-actions .el-button { margin-left: 0; font-size: 11px; }
.notes-format-row { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin: 10px 0 8px; }
.notes-share-info { color: #8a9fb0; font-size: 10px; }
.notes-title-input { margin-bottom: 8px; }
.notes-title-input :deep(.el-input__wrapper) { padding: 4px 10px; }
.notes-title-input :deep(.el-input__inner) { color: #1e3a4d; font-size: 15px; font-weight: 600; }
.notes-content-editor { flex: 1; min-height: 0; display: flex; }
.notes-content-editor :deep(.el-textarea) { flex: 1; display: flex; }
.notes-content-editor :deep(.el-textarea__inner) {
  flex: 1; min-height: 260px; max-height: none;
  padding: 10px 12px; border-radius: 8px;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; font-size: 13px; line-height: 1.8;
}
.notes-preview {
  flex: 1; min-height: 260px; max-height: min(56vh, 560px); overflow: auto;
  padding: 6px 14px; border: 1px solid #e5eef5; border-radius: 8px; background: #fff;
}
.notes-preview pre { margin: 0; white-space: pre-wrap; color: #405c70; font-family: inherit; font-size: 13px; line-height: 1.8; }
.markdown-body { color: #344e61; font-size: 13px; line-height: 1.8; }
.markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5 { margin: 14px 0 7px; color: #17384d; }
.markdown-body h2 { font-size: 18px; }
.markdown-body h3 { font-size: 16px; }
.markdown-body h4, .markdown-body h5 { font-size: 14px; }
.markdown-body p { margin: 6px 0; }
.markdown-body .md-empty { margin: 3px 0; }
.markdown-body ul { margin: 6px 0; padding-left: 20px; }
.markdown-body code { padding: 1px 4px; border-radius: 3px; background: #eef6fb; color: #0e7490; font-family: Consolas, monospace; }
.markdown-body pre { padding: 10px 12px; border-radius: 7px; background: #0b1d2e; overflow: auto; }
.markdown-body pre code { padding: 0; background: transparent; color: #b9e9f8; }
.markdown-body strong { color: #17384d; }
.notes-editor-foot {
  display: flex; justify-content: space-between; gap: 10px;
  padding-top: 7px; color: #9aacba; font-size: 9px;
}
.share-dialog-info { margin-bottom: 10px; color: #405c70; font-size: 13px; }
.share-dialog-hint { margin-top: 10px; padding: 9px 10px; border-radius: 7px; background: #f5faff; color: #788fa2; font-size: 10px; line-height: 1.6; }

.capture-layout { display: flex; flex-direction: column; gap: 12px; }
.capture-layout .panel { border: 1px solid #e4eef6; border-radius: 9px; background: #fbfdff; }
.capture-config { padding: 14px 16px; }
.capture-config-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.capture-config-head strong { display: block; color: #24425b; font-size: 13px; }
.capture-config-head span { display: block; margin-top: 4px; color: #91a4b4; font-size: 10px; }
.capture-form-row { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 9px; margin-top: 13px; }
.capture-field { display: flex; align-items: center; gap: 5px; flex-shrink: 0; }
.capture-field > span { color: #7d94a5; font-size: 10px; white-space: nowrap; }
.capture-field > small { color: #9aacba; font-size: 9px; }
.capture-interface { flex: 1; min-width: 260px; }
.capture-interface :deep(.el-select) { flex: 1; }
.capture-filter { flex: 1; min-width: 180px; }
.capture-filter :deep(.el-input) { flex: 1; }
.capture-if-option { display: flex; flex-direction: column; gap: 2px; }
.capture-if-option span { color: #24425b; font-size: 12px; }
.capture-if-option small { color: #91a4b4; font-size: 9px; }
.capture-config-hint { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 8px; color: #94a8b7; font-size: 9px; line-height: 1.5; }
.capture-config .el-alert { margin-top: 9px; }
.capture-metrics { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
.capture-metric { padding: 10px 12px; border: 1px solid #e4eef6; border-radius: 8px; background: #fbfdff; }
.capture-metric span { display: block; color: #91a4b4; font-size: 9px; }
.capture-metric b { display: block; margin-top: 5px; color: #24425b; font-family: Consolas, monospace; font-size: 16px; font-weight: 600; }
.capture-metric b small { color: #91a4b4; font-size: 9px; font-weight: 400; }
.capture-live { color: #059669 !important; }
.capture-ok { color: #0e7490 !important; }
.capture-error { color: #dc2626 !important; }
.capture-analysis-grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(260px, 0.7fr); gap: 12px; }
.capture-findings, .capture-side, .capture-talker-card { padding: 0; overflow: hidden; }
.capture-section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 11px 14px; border-bottom: 1px solid #eef4f8; }
.capture-section-head > div { display: flex; align-items: baseline; gap: 8px; }
.capture-section-head strong { display: flex; align-items: center; gap: 5px; color: #24425b; font-size: 12px; }
.capture-section-head strong .el-icon { color: #f59e0b; }
.capture-section-head span { color: #9aacba; font-size: 9px; }
.capture-findings :deep(.el-table), .capture-talker-card :deep(.el-table) { font-size: 10px; }
.capture-finding-title { display: block; color: #344e61; font-size: 10px; }
.capture-finding-desc { display: block; margin-top: 2px; color: #8da2b2; font-size: 9px; line-height: 1.4; }
.capture-mono { display: block; color: #38566b; font-family: Consolas, monospace; font-size: 10px; }
.capture-mac { display: block; margin-top: 2px; color: #91a4b4; font-family: Consolas, monospace; font-size: 9px; }
.capture-device { display: block; color: #0e7490; font-size: 10px; }
.capture-unmatched { display: block; color: #b0bdc7; font-size: 9px; }
.capture-side { min-width: 0; }
.capture-protocols { display: flex; flex-wrap: wrap; gap: 5px; padding: 12px 14px 6px; }
.capture-protocol { display: flex; align-items: center; gap: 4px; padding: 4px 7px; border-radius: 4px; background: #eef8fd; }
.capture-protocol b { color: #0e7490; font-size: 10px; }
.capture-protocol em { color: #7d94a5; font-size: 9px; font-style: normal; }
.capture-flags { display: flex; flex-wrap: wrap; gap: 6px; padding: 5px 14px 10px; }
.capture-flags span { color: #8499aa; font-size: 9px; }
.capture-flags b { color: #38566b; font-family: Consolas, monospace; }
.capture-side-foot { margin-top: 3px; padding: 9px 14px 12px; border-top: 1px solid #eef4f8; color: #91a4b4; font-size: 9px; line-height: 1.5; }
.capture-side-foot b { color: #38566b; }
.capture-talkers-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.capture-port-list { display: flex; flex-wrap: wrap; gap: 5px; padding: 7px 14px 12px; border-top: 1px solid #eef4f8; }
.capture-port-list span { padding: 2px 5px; border-radius: 3px; color: #7d94a5; background: #f4f9fc; font-family: Consolas, monospace; font-size: 9px; }
.capture-port-list b { color: #38566b; }
.capture-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 220px; padding: 30px; text-align: center; }
.capture-empty-icon { width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px; border-radius: 13px; color: #0ea5e9; background: #e8f7fe; font-size: 24px; }
.capture-empty strong { color: #45657b; font-size: 13px; }
.capture-empty p { max-width: 540px; margin: 7px 0 0; color: #91a4b4; font-size: 10px; line-height: 1.7; }

.capture-history { overflow: hidden; }
.capture-history-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 11px 14px; border-bottom: 1px solid #eef4f8; }
.capture-history-head strong { display: flex; align-items: center; gap: 5px; color: #24425b; font-size: 12px; }
.capture-history-head strong .el-icon { color: #0ea5e9; }
.capture-history-head span { display: block; margin-top: 3px; color: #9aacba; font-size: 9px; }
.capture-history-actions { display: flex; flex-shrink: 0; gap: 6px; }
.capture-history :deep(.el-table) { font-size: 10px; }
.capture-record-name { color: #38566b; font-family: Consolas, monospace; font-size: 9px; }
.capture-history :deep(.el-table .cell) { line-height: 1.35; }

@media (max-width: 1180px) {
  .capture-metrics { grid-template-columns: repeat(3, 1fr); }
  .capture-analysis-grid { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .capture-form-row { align-items: stretch; flex-direction: column; }
  .capture-field { width: 100%; }
  .capture-field :deep(.el-input), .capture-field :deep(.el-select), .capture-field :deep(.el-input-number) { flex: 1; width: auto; }
  .capture-talkers-grid { grid-template-columns: 1fr; }
  .capture-metrics { grid-template-columns: repeat(2, 1fr); }
  .capture-config-head { flex-direction: column; }
}


@media (max-width: 1180px) {
  .sftp-layout { grid-template-columns: 300px minmax(0, 1fr); }
  .ssh-layout { grid-template-columns: 320px minmax(0, 1fr); }
}

.tools-view {
  min-height: calc(100vh - 155px);
  display: flex;
  flex-direction: column;
}

.tools-card {
  flex: 1;
  min-height: calc(100vh - 175px);
  display: flex;
  flex-direction: column;
}

.tools-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 18px 22px;
}

.tools-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.tools-tabs :deep(.el-tabs__header) {
  flex-shrink: 0;
  margin-bottom: 14px;
}

.tools-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.tools-tabs :deep(.el-tabs__item) {
  font-size: 13px;
  padding: 0 18px;
}

@media (max-width: 1000px) {
  .tool-grid, .tool-grid.wide { grid-template-columns: 1fr 1fr; }
  .ssh-layout, .sftp-layout { grid-template-columns: 1fr; }
  .terminal-host { height: 360px; }
  .tools-card :deep(.el-card__body) { padding: 14px; }
  .notes-layout { grid-template-columns: 1fr; min-height: 0; }
  .notes-side { max-height: 280px; }
  .notes-editor { min-height: 420px; }
}
@media (max-width: 680px) {
  .tools-header { align-items: flex-start; flex-direction: column; }
  .tool-grid, .tool-grid.wide, .subnet-grid { grid-template-columns: 1fr; }
  .subnet-inputs { flex-wrap: wrap; }
  .tools-tabs :deep(.el-tabs__item) { padding: 0 10px; font-size: 12px; }
  .sftp-upload-card { align-items: flex-start; }
  .notes-editor-head { flex-direction: column; }
  .notes-editor-actions { width: 100%; }
}

.subnet-big strong,
.subnet-grid b,
.subnet-binary code {
  overflow-wrap: anywhere;
  word-break: break-word;
}

/* 子网换算双栏：左 IPv4 / 右 IPv6，窄屏自动上下排列 */
.subnet-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
}

.subnet-panel {
  min-width: 0;
  padding: 14px;
  border: 1px solid #e4eef6;
  border-radius: 10px;
  background: #fbfdff;
}

.subnet-panel .tool-intro {
  min-height: 62px;
}

.subnet-panel .subnet-inputs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  max-width: none;
  margin: 14px 0;
}

.subnet-panel .subnet-ip {
  flex: 1 1 220px;
  min-width: 180px;
}

.subnet-panel .subnet-prefix {
  width: 104px;
}

.subnet-panel .subnet-hint {
  flex-basis: 100%;
  margin-top: -2px;
}

.subnet-panel .subnet-results {
  max-width: none;
}

.subnet-panel .subnet-big {
  flex-wrap: wrap;
  padding: 12px 13px;
}

.subnet-panel .subnet-big strong {
  font-size: 21px;
  line-height: 1.25;
}

.subnet-panel .subnet-big small {
  margin-left: auto;
}

.subnet-panel .subnet-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.subnet-panel .subnet-binary code {
  display: block;
  margin-top: 3px;
  line-height: 1.65;
}

.subnet-proto-badge {
  display: inline-flex;
  align-items: center;
  margin-right: 4px;
  padding: 1px 6px;
  border-radius: 4px;
  color: #0369a1;
  background: #e0f2fe;
  font-family: Consolas, monospace;
  font-size: 10px;
  vertical-align: 1px;
}

.subnet-proto-badge.ipv6 {
  color: #6d28d9;
  background: #ede9fe;
}

@media (max-width: 1100px) {
  .subnet-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 700px) {
  .subnet-panel {
    padding: 10px;
  }

  .subnet-panel .subnet-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .subnet-panel .subnet-big strong {
    font-size: 17px;
  }

  .subnet-panel .subnet-prefix {
    width: 92px;
  }
}
</style>
