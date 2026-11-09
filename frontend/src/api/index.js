import axios from 'axios'
import { getToken } from '@/store/auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求：自动携带登录令牌
api.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 统一错误提示 + 登录失效跳转
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err?.response?.data?.detail
    if (detail) err.message = detail

    if (err?.response?.status === 401) {
      localStorage.removeItem('nms_token')
      localStorage.removeItem('nms_user')
      localStorage.removeItem('nms_remember')
      sessionStorage.removeItem('nms_token')
      sessionStorage.removeItem('nms_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }

    // 授权到期：清除现有会话并回到登录页，不允许继续使用管理界面
    const licenseExpired = err?.response?.status === 403 && (
      err?.response?.data?.code === 'license_expired'
      || String(detail || '').includes('商业授权已到期')
    )
    if (licenseExpired) {
      localStorage.removeItem('nms_token')
      localStorage.removeItem('nms_user')
      localStorage.removeItem('nms_remember')
      sessionStorage.removeItem('nms_token')
      sessionStorage.removeItem('nms_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login?license=expired'
      }
    }
    return Promise.reject(err)
  }
)

// 资产相关API
export const assetApi = {
  getList(params) {
    return api.get('/assets/', { params })
  },
  groups() {
    return api.get('/assets/groups')
  },
  createGroup(data) {
    return api.post('/assets/groups', data)
  },
  getOne(id) {
    return api.get(`/assets/${id}`)
  },
  create(data) {
    return api.post('/assets/', data)
  },
  update(id, data) {
    return api.put(`/assets/${id}`, data)
  },
  delete(id) {
    return api.delete(`/assets/${id}`)
  },
  bulkUpdate(ids, fields) {
    return api.post('/assets/bulk-update', { ids, fields })
  },
  bulkDelete(ids) {
    return api.post('/assets/bulk-delete', { ids })
  },
  toggle(id) {
    return api.put(`/assets/${id}/toggle`)
  },
  testSnmp(data) {
    return api.post('/snmp/test', data)
  },
  testProbe(data) {
    return api.post('/assets/test-probe', data, { timeout: 30000 })
  },
  testOid(data) {
    return api.post('/snmp/test-oid', data, { timeout: 60000 })
  },
  // 上传设备自定义图标（FormData: file）
  uploadIcon(formData) {
    return api.post('/assets/icons', formData, { timeout: 60000 })
  },
  // 内置图标库 + 厂商匹配 + 批量套用图标
  iconPresets() {
    return api.get('/assets/icon-presets')
  },
  matchIcons(data = {}) {
    return api.post('/assets/match-icons', data)
  },
  applyIcon(data) {
    return api.post('/assets/apply-icon', data)
  },
  // 导入（FormData: file / mode / auto_create_cabinet）
  importAssets(formData) {
    return api.post('/assets/import', formData, { timeout: 120000 })
  },
  // ---- 维保记录 ----
  listMaintenance(deviceId) {
    return api.get(`/assets/${deviceId}/maintenance`)
  },
  addMaintenance(deviceId, data) {
    return api.post(`/assets/${deviceId}/maintenance`, data)
  },
  removeMaintenance(maintenanceId) {
    return api.delete(`/assets/maintenance/${maintenanceId}`)
  },
  // ---- 资产标签二维码 ----
  getQrcode(deviceId, kind = 'url') {
    return api.get(`/assets/${deviceId}/qrcode`, { params: { kind } })
  },
}

// 监控相关API
export const healthApi = {
  check() {
    return api.get('/health')
  },
}

export const monitorApi = {
  getDashboard() {
    return api.get('/dashboard')
  },
  getDeviceOverview(deviceId) {
    return api.get(`/monitor/devices/${deviceId}/overview`)
  },
  collectDevice(deviceId) {
    return api.post(`/monitor/devices/${deviceId}/collect`)
  },
  getMetricHistory(deviceId, params) {
    return api.get(`/monitor/devices/${deviceId}/history`, { params })
  },
  getInterfaces(deviceId) {
    return api.get(`/monitor/devices/${deviceId}/interfaces`)
  },
  getInterfaceSummaries(deviceIds = []) {
    const ids = Array.isArray(deviceIds) ? deviceIds.filter(Boolean).join(',') : deviceIds
    return api.get('/monitor/interface-summaries', { params: ids ? { device_ids: ids } : {} })
  },
  getInterfaceHistory(deviceId, interfaceId, params) {
    return api.get(`/monitor/devices/${deviceId}/interfaces/${interfaceId}/history`, { params })
  },
  getAlerts(deviceId, params) {
    return api.get(`/monitor/devices/${deviceId}/alerts`, { params })
  },
  acknowledgeAlert(alertId, source = 'device') {
    return api.post(`/monitor/alerts/${alertId}/ack`, null, { params: { source } })
  },
  deleteAlert(alertId, source = 'device') {
    return api.delete(`/monitor/alerts/${alertId}`, { params: { source } })
  },
  bulkDeleteAlerts(items) {
    return api.post('/monitor/alerts/bulk-delete', { items })
  },
  getHiddenAlerts(params = {}) {
    return api.get('/monitor/alerts/hidden', { params })
  },
  hideAlert(alertId, source = 'device') {
    return api.post(`/monitor/alerts/${alertId}/hide`, null, { params: { source } })
  },
  restoreAlert(alertId, source = 'device') {
    return api.post(`/monitor/alerts/${alertId}/restore`, null, { params: { source } })
  },
  probeAlert(alertId) {
    return api.post(`/monitor/alerts/${alertId}/probe`, {}, { timeout: 60000 })
  },
  getUnackAlerts() {
    return api.get('/monitor/alerts/unacknowledged')
  },
  getActiveAlerts() {
    return api.get('/monitor/alerts/active')
  },
  getBroadcastAlerts() {
    return api.get('/monitor/alerts/broadcast')
  },
  listAlerts(params) {
    return api.get('/monitor/alerts', { params })
  },
  getSuppressions() {
    return api.get('/monitor/suppressions')
  },
  suppressAlert(alertId, params) {
    return api.post(`/monitor/alerts/${alertId}/suppress`, null, { params })
  },
  createSuppression(data) {
    return api.post('/monitor/suppressions', data)
  },
  deleteSuppression(id) {
    return api.delete(`/monitor/suppressions/${id}`)
  },
  getAlertTrend() {
    return api.get('/dashboard/alert-trend')
  },
}

// 拓扑相关API
export const topologyApi = {
  getTopology() {
    return api.get('/topology/')
  },
  discover() {
    return api.post('/topology/discover')
  },
  addConnection(data) {
    return api.post('/topology/add-connection', data)
  },
  getDeviceInterfaces(deviceId) {
    return api.get(`/monitor/devices/${deviceId}/interfaces`)
  },
  deleteConnection(id) {
    return api.delete(`/topology/connection/${id}`)
  },
  /** 保存手动布局：{nodes:[{device_id,x,y}]} 或 {reset:true} */
  saveLayout(data) {
    return api.put('/topology/layout', data)
  },
}

// 网站监控API
export const websiteApi = {
  getList(params) {
    return api.get('/website/targets', { params })
  },
  getOne(id) {
    return api.get(`/website/targets/${id}`)
  },
  create(data) {
    return api.post('/website/targets', data)
  },
  update(id, data) {
    return api.put(`/website/targets/${id}`, data)
  },
  remove(id) {
    return api.delete(`/website/targets/${id}`)
  },
  toggle(id) {
    return api.put(`/website/targets/${id}/toggle`)
  },
  categories() {
    return api.get('/website/targets/categories')
  },
  reorder(ids) {
    return api.put('/website/targets/reorder', { ids })
  },
  importTargets(file, mode = 'skip') {
    const form = new FormData()
    form.append('file', file)
    form.append('mode', mode)
    return api.post('/website/targets/import', form, { timeout: 120000 })
  },
  exportUrl() {
    return '/api/website/targets/export'
  },
  getHistory(id, params) {
    return api.get(`/website/targets/${id}/history`, { params })
  },
  getStats(id, params) {
    return api.get(`/website/targets/${id}/stats`, { params })
  },
  getAlerts(id, params) {
    return api.get(`/website/targets/${id}/alerts`, { params })
  },
  certificates(params) {
    return api.get('/website/certificates', { params })
  },
  certificateConfig() {
    return api.get('/website/certificates/config')
  },
  certbotStatus() {
    return api.get('/website/certificates/certbot/status')
  },
  installCertbot() {
    return api.post('/website/certificates/certbot/install', null, { timeout: 700000 })
  },
  certificate(id) {
    return api.get(`/website/certificates/${id}`)
  },
  importCertificate(form) {
    return api.post('/website/certificates/import', form, { timeout: 120000 })
  },
  generateCertificate(data) {
    return api.post('/website/certificates/generate', data, { timeout: 120000 })
  },
  applyCertificate(data) {
    return api.post('/website/certificates/apply', data, { timeout: 210000 })
  },
  refreshCertificate(id) {
    return api.post(`/website/certificates/${id}/refresh`)
  },
  refreshCertificates() {
    return api.post('/website/certificates/refresh', null, { timeout: 180000 })
  },
  renewCertificate(id) {
    return api.post(`/website/certificates/${id}/renew`, null, { timeout: 210000 })
  },
  updateCertificate(id, data) {
    return api.put(`/website/certificates/${id}`, data)
  },
  deleteCertificate(id) {
    return api.delete(`/website/certificates/${id}`)
  },
  certificateDownloadUrl(id, kind = 'cert') {
    return `/api/website/certificates/${id}/download?kind=${encodeURIComponent(kind)}&token=${encodeURIComponent(getToken())}`
  },
  ackAlert(alertId) {
    return api.post(`/website/alerts/${alertId}/ack`)
  },
}

// 仪表盘 / 拓扑图 / 大屏共享
export const sharingApi = {
  users() {
    return api.get('/sharing/users')
  },
  owned(resourceType) {
    return api.get('/sharing/owned', { params: { resource_type: resourceType } })
  },
  sharedWithMe(resourceType) {
    return api.get('/sharing/shared-with-me', { params: { resource_type: resourceType } })
  },
  saveResource(data) {
    return api.post('/sharing/resources', data)
  },
  resource(id) {
    return api.get(`/sharing/resources/${id}`)
  },
  updateResource(id, data) {
    return api.put(`/sharing/resources/${id}`, data)
  },
  deleteResource(id) {
    return api.delete(`/sharing/resources/${id}`)
  },
  saveMembers(id, userIds) {
    return api.post(`/sharing/resources/${id}/members`, { user_ids: userIds })
  },
  removeMember(id, userId) {
    return api.delete(`/sharing/resources/${id}/members/${userId}`)
  },
  requestEdit(id, message = '') {
    return api.post(`/sharing/resources/${id}/edit-request`, { message })
  },
  requests() {
    return api.get('/sharing/requests')
  },
  approveRequest(id) {
    return api.post(`/sharing/requests/${id}/approve`)
  },
  rejectRequest(id) {
    return api.post(`/sharing/requests/${id}/reject`)
  },
}

// 资产告警规则API
export const alertRuleApi = {
  list(deviceId) {
    return api.get('/alert-rules', { params: { device_id: deviceId } })
  },
  channels() {
    return api.get('/alert-rules/channels')
  },
  create(data) {
    return api.post('/alert-rules', data)
  },
  update(id, data) {
    return api.put(`/alert-rules/${id}`, data)
  },
  remove(id) {
    return api.delete(`/alert-rules/${id}`)
  },
}

// 告警通知API
export const notificationApi = {
  getChannels() {
    return api.get('/notifications/channels')
  },
  createChannel(data) {
    return api.post('/notifications/channels', data)
  },
  updateChannel(id, data) {
    return api.put(`/notifications/channels/${id}`, data)
  },
  deleteChannel(id) {
    return api.delete(`/notifications/channels/${id}`)
  },
  testChannel(id) {
    return api.post(`/notifications/channels/${id}/test`)
  },
  testInline(data) {
    return api.post('/notifications/test', data)
  },
  dispatchTest(data) {
    return api.post('/notifications/dispatch-test', data || {})
  },
  getLogs(params) {
    return api.get('/notifications/logs', { params })
  },
  upstreamSettings() {
    return api.get('/notifications/upstream/settings')
  },
  createUpstreamToken() {
    return api.post('/notifications/upstream/token')
  },
  upstreamReceived(limit = 20) {
    return api.get('/notifications/upstream/received', { params: { limit } })
  },
}

// 设备自动发现API
export const discoveryApi = {
  scanSnmp(data) {
    return api.post('/discovery/snmp/scan', data, { timeout: 180000 })
  },
  addSnmp(data) {
    return api.post('/discovery/snmp/add', data, { timeout: 180000 })
  },
  scanPing(data) {
    return api.post('/discovery/ping/scan', data, { timeout: 180000 })
  },
  getSchedule() {
    return api.get('/discovery/schedule')
  },
  saveSchedule(data) {
    return api.put('/discovery/schedule', data)
  },
  runSchedule() {
    return api.post('/discovery/schedule/run', {}, { timeout: 180000 })
  },
  listSchedules() {
    return api.get('/discovery/schedules')
  },
  createSchedule(data) {
    return api.post('/discovery/schedules', data)
  },
  updateSchedule(id, data) {
    return api.put(`/discovery/schedules/${id}`, data)
  },
  deleteSchedule(id) {
    return api.delete(`/discovery/schedules/${id}`)
  },
  runScheduleById(id) {
    return api.post(`/discovery/schedules/${id}/run`, {}, { timeout: 180000 })
  },
}

// 系统工具API
export const toolsApi = {
  snmpwalk(data) {
    return api.post('/tools/snmpwalk', data, { timeout: 120000 })
  },
  ping(data) {
    return api.post('/tools/ping', data, { timeout: 120000 })
  },
  tracert(data) {
    return api.post('/tools/tracert', data, { timeout: 120000 })
  },
  publicIp(force = false) {
    return api.get('/tools/public-ip', { params: force ? { force: true } : {}, timeout: 30000 })
  },
  sftpList(data) {
    return api.post('/tools/sftp/list', data, { timeout: 60000 })
  },
  sftpUpload(formData, onUploadProgress) {
    return api.post('/tools/sftp/upload', formData, {
      timeout: 300000,
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress,
    })
  },
  sftpDownload(data) {
    return api.post('/tools/sftp/download', data, { timeout: 300000, responseType: 'blob' })
  },
  captureInterfaces() {
    return api.get('/tools/capture/interfaces')
  },
  captureStart(data) {
    return api.post('/tools/capture/start', data)
  },
  captureStatus(jobId) {
    return api.get(`/tools/capture/status/${encodeURIComponent(jobId)}`)
  },
  captureStop(jobId) {
    return api.post(`/tools/capture/stop/${encodeURIComponent(jobId)}`)
  },
  captureRecords() {
    return api.get('/tools/capture/records')
  },
  captureRecordDownload(recordId) {
    return api.get(`/tools/capture/records/${recordId}/download`, { responseType: 'blob' })
  },
  captureRecordsBatchDownload(ids) {
    return api.post('/tools/capture/records/batch-download', { ids }, { responseType: 'blob' })
  },
  captureRecordsBatchDelete(ids) {
    return api.post('/tools/capture/records/batch-delete', { ids })
  },
}

// 商业授权API
export const licenseApi = {
  verifyBrandingPrivilege(token) {
    return api.post('/license/privilege/verify', { token })
  },
  publicStatus() {
    return api.get('/license/public-status')
  },
  info() {
    return api.get('/license')
  },
  activate(token) {
    return api.post('/license/activate', { token })
  },
  activatePublic(token) {
    return api.post('/license/activate-public', { token })
  },
  deactivate() {
    return api.delete('/license')
  },
}

// 运维笔记API
export const notesApi = {
  list() {
    return api.get('/notes')
  },
  users() {
    return api.get('/notes/users')
  },
  create(data) {
    return api.post('/notes', data)
  },
  update(id, data) {
    return api.put(`/notes/${id}`, data)
  },
  remove(id) {
    return api.delete(`/notes/${id}`)
  },
  share(id, userIds) {
    return api.post(`/notes/${id}/share`, { user_ids: userIds })
  },
  batchDelete(ids) {
    return api.post('/notes/batch-delete', { ids })
  },
  batchShare(ids, userIds) {
    return api.post('/notes/batch-share', { ids, user_ids: userIds })
  },
  copy(id) {
    return api.post(`/notes/${id}/copy`)
  },
}

// 机房与机柜API
export const roomApi = {
  list() {
    return api.get('/rooms/')
  },
  get(id) {
    return api.get(`/rooms/${id}`)
  },
  create(data) {
    return api.post('/rooms/', data)
  },
  update(id, data) {
    return api.put(`/rooms/${id}`, data)
  },
  remove(id) {
    return api.delete(`/rooms/${id}`)
  },
  layout(id) {
    return api.get(`/rooms/${id}/layout`)
  },
  listCabinets(roomId) {
    return api.get(`/rooms/${roomId}/cabinets`)
  },
  createCabinet(data) {
    return api.post('/rooms/cabinets', data)
  },
  updateCabinet(id, data) {
    return api.put(`/rooms/cabinets/${id}`, data)
  },
  removeCabinet(id) {
    return api.delete(`/rooms/cabinets/${id}`)
  },
  setDoor(id, state) {
    return api.put(`/rooms/cabinets/${id}/door`, null, { params: { state } })
  },
  cabinetUsage(id) {
    return api.get(`/rooms/cabinets/${id}/usage`)
  },
  // ---- 电子锁 ----
  lockStatus(cabinetId) {
    return api.get(`/rooms/cabinets/${cabinetId}/lock-status`)
  },
  lockAction(cabinetId, action) {
    return api.put(`/rooms/cabinets/${cabinetId}/lock`, null, { params: { action } })
  },
  updateLockConfig(cabinetId, data) {
    return api.put(`/rooms/cabinets/${cabinetId}/lock-config`, data)
  },
  accessLogs(cabinetId, limit = 20) {
    return api.get(`/rooms/cabinets/${cabinetId}/access-logs`, { params: { limit } })
  },
  // ---- 温湿度传感器 ----
  sensors(roomId) {
    return api.get(`/rooms/${roomId}/sensors`)
  },
  sensorSummary(roomId) {
    return api.get(`/rooms/${roomId}/sensor-summary`)
  },
  createSensor(roomId, data) {
    return api.post(`/rooms/${roomId}/sensors`, data)
  },
  updateSensor(sensorId, data) {
    return api.put(`/rooms/sensors/${sensorId}`, data)
  },
  removeSensor(sensorId) {
    return api.delete(`/rooms/sensors/${sensorId}`)
  },
  sensorReadings(sensorId, hours = 24) {
    return api.get(`/rooms/sensors/${sensorId}/readings`, { params: { hours } })
  },
}

// 认证
export const authApi = {
  login(data) {
    return api.post('/auth/login', data)
  },
  me() {
    return api.get('/auth/me')
  },
  changePassword(data) {
    return api.post('/auth/change-password', data)
  },
}

// 用户 / 角色 / 群组
export const userApi = {
  me() {
    return api.get('/users/me')
  },
  updateMe(data) {
    return api.put('/users/me', data)
  },
  list(params) {
    return api.get('/users', { params })
  },
  create(data) {
    return api.post('/users', data)
  },
  update(id, data) {
    return api.put(`/users/${id}`, data)
  },
  remove(id) {
    return api.delete(`/users/${id}`)
  },
  resetPassword(id, password) {
    return api.post(`/users/${id}/reset-password`, { password })
  },
  permissions() {
    return api.get('/users/permissions')
  },
}

export const roleApi = {
  list() {
    return api.get('/roles')
  },
  create(data) {
    return api.post('/roles', data)
  },
  update(id, data) {
    return api.put(`/roles/${id}`, data)
  },
  remove(id) {
    return api.delete(`/roles/${id}`)
  },
}

export const groupApi = {
  list() {
    return api.get('/groups')
  },
  create(data) {
    return api.post('/groups', data)
  },
  update(id, data) {
    return api.put(`/groups/${id}`, data)
  },
  remove(id) {
    return api.delete(`/groups/${id}`)
  },
}

// MIB 管理
export const mibApi = {
  list() {
    return api.get('/mibs')
  },
  upload(formData) {
    return api.post('/mibs/upload', formData, { timeout: 120000 })
  },
  get(id) {
    return api.get(`/mibs/${id}`)
  },
  objects(id, params) {
    return api.get(`/mibs/${id}/objects`, { params })
  },
  recommendations(id) {
    return api.get(`/mibs/${id}/recommendations`)
  },
  importStandard() {
    return api.post('/mibs/import-standard')
  },
  builtinCatalog() {
    return api.get('/mibs/builtin/catalog')
  },
  importBuiltin(keys) {
    return api.post('/mibs/builtin/import', keys ? { keys } : { all: true })
  },
  templates(params) {
    return api.get('/mibs/templates', { params })
  },
  matchTemplate(params) {
    return api.get('/mibs/templates/match', { params })
  },
  applyTemplate(data) {
    return api.post('/mibs/templates/apply', data)
  },
  autoMatch(data) {
    return api.post('/mibs/auto-match', data, { timeout: 180000 })
  },
  autoBind(data) {
    return api.post('/mibs/auto-bind', data, { timeout: 30000 })
  },
  remove(id) {
    return api.delete(`/mibs/${id}`)
  },
  batchDelete(ids) {
    return api.delete('/mibs/batch/delete', { data: { ids } })
  },
  assignDevices(id, deviceIds) {
    return api.post(`/mibs/${id}/devices/assign`, { device_ids: deviceIds })
  },
}

// 大屏外部数据源
export const bigscreenApi = {
  zabbixQuery(data) {
    return api.post('/bigscreen/zabbix/query', data, { timeout: 60000 })
  },
}

// 系统配置
export const settingsApi = {
  publicSettings() {
    return api.get('/settings/public', { params: { _t: Date.now() } })
  },
  version() {
    return api.get('/settings/version')
  },
  getCaptcha() {
    return api.get('/settings/captcha', { params: { _t: Date.now() } })
  },
  get() {
    return api.get('/settings')
  },
  update(settings, privilegeToken = '') {
    return api.put('/settings', privilegeToken
      ? { settings, privilege_token: privilegeToken }
      : { settings })
  },
  integrationTest() {
    return api.post('/settings/integration/test')
  },
  redisTest() {
    return api.post('/settings/redis/test')
  },
  securityInfo() {
    return api.get('/settings/security-info')
  },
  startupStatus() {
    return api.get('/settings/startup', { params: { _t: Date.now() } })
  },
  updateStartup(enabled) {
    return api.put('/settings/startup', { enabled: !!enabled })
  },
  webAccessStatus() {
    return api.get('/settings/web-access/status')
  },
  applyWebAccess() {
    return api.post('/settings/web-access/apply')
  },
  diagnoseWebAccess() {
    return api.get('/settings/web-access/diagnose')
  },
  uploadWebCertificate(form) {
    return api.post('/settings/web-access/certificate', form, { timeout: 120000 })
  },
  getAlertSound() {
    return api.get('/settings/alert-sound')
  },
  uploadAlertSound(file, level = 'emergency') {
    const form = new FormData()
    form.append('file', file)
    return api.post('/settings/alert-sound', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { level },
      timeout: 60000,
    })
  },
  deleteAlertSound(level = 'emergency') {
    return api.delete('/settings/alert-sound', { params: { level } })
  },
  resetAllAlertSounds() {
    return api.delete('/settings/alert-sound/all')
  },
  getLogo() {
    return api.get('/settings/logo')
  },
  uploadLogo(file) {
    const form = new FormData()
    form.append('file', file)
    return api.post('/settings/logo', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  },
  deleteLogo() {
    return api.delete('/settings/logo')
  },
  exportConfig() {
    return api.get('/settings/export', { responseType: 'blob' })
  },
  importConfig(formData, dryRun = false, privilegeToken = '') {
    if (privilegeToken) formData.append('privilege_token', privilegeToken)
    return api.post('/settings/import', formData, {
      params: { dry_run: dryRun },
      timeout: 120000,
    })
  },
  forwardStatus() {
    return api.get('/logs/forward/status')
  },
  forwardTest() {
    return api.post('/logs/forward/test')
  },
  recentLogs(params) {
    return api.get('/logs/recent', { params })
  },
}

// 审计日志
export const auditApi = {
  meta() {
    return api.get('/audit/meta')
  },
  logs(params) {
    return api.get('/audit/logs', { params })
  },
  export(params) {
    return api.get('/audit/export', { params, responseType: 'blob' })
  },
  cleanup(days) {
    return api.delete('/audit/cleanup', { params: { days } })
  },
}

// 系统维护（数据库备份）
export const systemApi = {
  hostStatus() {
    return api.get('/system/host-status')
  },
  backups() {
    return api.get('/system/backups')
  },
  createBackup() {
    return api.post('/system/backups', {}, { timeout: 300000 })
  },
  removeBackup(name) {
    return api.delete(`/system/backups/${encodeURIComponent(name)}`)
  },
  downloadUrl(name) {
    return `/api/system/backups/${encodeURIComponent(name)}/download`
  },
  collectDebug(data = {}) {
    return api.post('/system/debug/collect', data, { timeout: 180000 })
  },
  debugDownloadUrl(name) {
    return `/api/system/debug/${encodeURIComponent(name)}/download`
  },
  updateInfo() {
    return api.get('/system/update')
  },
  saveUpdateConfig(onlineUrl) {
    return api.put('/system/update/config', { online_url: onlineUrl })
  },
  checkOnlineUpdate() {
    return api.post('/system/update/check', {}, { timeout: 120000 })
  },
  startOnlineUpdate() {
    return api.post('/system/update/online', {}, { timeout: 120000 })
  },
  rollbackVersion(backupId, force = false) {
    return api.post('/system/update/rollback', { backup_id: backupId, force }, { timeout: 120000 })
  },
  backupFiles(backupId) {
    return api.get(`/system/update/backups/${encodeURIComponent(backupId)}/files`)
  },
  deleteBackup(backupId) {
    return api.delete(`/system/update/backups/${encodeURIComponent(backupId)}`)
  },
  uploadUpdate(file, { force = false, onProgress } = {}) {
    const form = new FormData()
    form.append('file', file)
    return api.post('/system/update/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { force },
      timeout: 300000,
      onUploadProgress: onProgress,
    })
  },
  updateStatus(jobId = '') {
    return api.get('/system/update/status', { params: jobId ? { job_id: jobId } : {} })
  },
  publicUpdateStatus(jobId, token) {
    return axios.get(`/api/system/update/public-status/${encodeURIComponent(jobId)}`, { params: { token } })
  },
}

// 主机网络/服务/防火墙
export const networkApi = {
  overview() {
    return api.get('/network/overview')
  },
  configureAdapter(data) {
    return api.put('/network/adapter', data)
  },
  addRoute(data) {
    return api.post('/network/routes', data)
  },
  deleteRoute(data) {
    return api.post('/network/routes/delete', data)
  },
  setFirewall(data) {
    return api.post('/network/firewall', data)
  },
  restartNetwork(data = {}) {
    return api.post('/network/restart', data, { timeout: 90000 })
  },
  services(params) {
    return api.get('/network/services', { params })
  },
  serviceAction(data) {
    return api.post('/network/services/action', data)
  },
  scheduledTasks() {
    return api.get('/network/scheduled-tasks')
  },
  scheduledTaskAction(data) {
    return api.post('/network/scheduled-tasks/action', data)
  },
}

// 网络设备配置备份
export const configBackupApi = {
  overview() {
    return api.get('/config-backups/overview')
  },
  devices(params) {
    return api.get('/config-backups/devices', { params })
  },
  updateDevice(id, data) {
    return api.put(`/config-backups/devices/${id}`, data)
  },
  run(id) {
    return api.post(`/config-backups/devices/${id}/run`, {}, { timeout: 180000 })
  },
  batchRun(deviceIds) {
    return api.post('/config-backups/batch/run', { device_ids: deviceIds })
  },
  batchToggle(deviceIds, enabled) {
    return api.post('/config-backups/batch/toggle', { device_ids: deviceIds, backup_enabled: enabled })
  },
  batchAdd(deviceIds, data) {
    return api.post('/config-backups/devices/batch-add', { device_ids: deviceIds, ...data })
  },
  batchRemove(deviceIds) {
    return api.post('/config-backups/devices/batch-remove', { device_ids: deviceIds })
  },
  records(params) {
    return api.get('/config-backups/records', { params })
  },
  recordGroups(params) {
    return api.get('/config-backups/records/grouped', { params })
  },
  record(id) {
    return api.get(`/config-backups/records/${id}`)
  },
  deleteRecord(id) {
    return api.delete(`/config-backups/records/${id}`)
  },
  diff(aId, bId) {
    return api.get('/config-backups/diff', { params: { a_id: aId, b_id: bId } })
  },
  settings() {
    return api.get('/config-backups/settings')
  },
  saveSettings(data) {
    return api.put('/config-backups/settings', data)
  },
  downloadUrl(id) {
    return `/api/config-backups/records/${id}/download`
  },
  exportUrl(params = {}) {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(key, value)
    })
    const text = query.toString()
    return `/api/config-backups/export${text ? `?${text}` : ''}`
  },
}

// 设备巡检：任务 / 报告
export const credentialApi = {
  list(params = {}) {
    return api.get('/credentials', { params })
  },
  batchDelete(ids) {
    return api.post('/credentials/batch-delete', { ids })
  },
  importCredentials(formData) {
    return api.post('/credentials/import', formData, {
      timeout: 120000,
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  exportUrl(params = {}) {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
    })
    const text = query.toString()
    return `/api/credentials/export${text ? `?${text}` : ''}`
  },
  create(data) {
    return api.post('/credentials', data)
  },
  update(id, data) {
    return api.put(`/credentials/${id}`, data)
  },
  remove(id) {
    return api.delete(`/credentials/${id}`)
  },
}

export const inspectionApi = {
  overview() {
    return api.get('/inspection/overview')
  },
  inspectionSettings() {
    return api.get('/inspection/settings')
  },
  updateInspectionSettings(data) {
    return api.put('/inspection/settings', data)
  },
  vendorCommands(assetIds, vendors = []) {
    return api.get('/inspection/vendor-commands', {
      params: {
        asset_ids: (assetIds || []).join(','),
        vendors: (vendors || []).filter(Boolean).join(','),
      },
    })
  },
  tasks(params) {
    return api.get('/inspection/tasks', { params })
  },
  task(id) {
    return api.get(`/inspection/tasks/${id}`)
  },
  createTask(data) {
    return api.post('/inspection/tasks', data)
  },
  updateTask(id, data) {
    return api.put(`/inspection/tasks/${id}`, data)
  },
  deleteTask(id) {
    return api.delete(`/inspection/tasks/${id}`)
  },
  runTask(id) {
    return api.post(`/inspection/tasks/${id}/run`, {}, { timeout: 180000 })
  },
  stopTask(id) {
    return api.post(`/inspection/tasks/${id}/stop`)
  },
  reports(params) {
    return api.get('/inspection/reports', { params })
  },
  report(id) {
    return api.get(`/inspection/reports/${id}`)
  },
  previewReport(id) {
    return api.get(`/inspection/reports/${id}/preview`)
  },
  officeConfig(id) {
    return api.get(`/inspection/reports/${id}/office-config`)
  },
  deleteReport(id) {
    return api.delete(`/inspection/reports/${id}`)
  },
  uploadReport(formData) {
    return api.post('/inspection/reports/upload', formData, { timeout: 180000 })
  },
  downloadUrl(id) {
    return `/api/inspection/reports/${id}/download`
  },
}

// 集群与负载均衡
export const clusterApi = {
  status() {
    return api.get('/cluster/status')
  },
  updateConfig(settings) {
    return api.put('/cluster/config', { settings })
  },
  identity() {
    return api.get('/cluster/identity')
  },
  updateIdentity(data) {
    return api.put('/cluster/identity', data)
  },
  nodes() {
    return api.get('/cluster/nodes')
  },
  updateWeight(nodeId, weight) {
    return api.put(`/cluster/nodes/${encodeURIComponent(nodeId)}`, { weight })
  },
  removeNode(nodeId) {
    return api.delete(`/cluster/nodes/${encodeURIComponent(nodeId)}`)
  },
  lbConfig() {
    return api.get('/cluster/lb-config')
  },
}

// 虚拟化管理（VMware / KVM 只读纳管）
export const virtualizationApi = {
  platforms() {
    return api.get('/virtualization/platforms')
  },
  createPlatform(data) {
    return api.post('/virtualization/platforms', data)
  },
  updatePlatform(id, data) {
    return api.put(`/virtualization/platforms/${id}`, data)
  },
  deletePlatform(id) {
    return api.delete(`/virtualization/platforms/${id}`)
  },
  testPlatform(id) {
    return api.post(`/virtualization/platforms/${id}/test`)
  },
  syncPlatform(id) {
    return api.post(`/virtualization/platforms/${id}/sync`)
  },
  syncAll() {
    return api.post('/virtualization/sync')
  },
  overview() {
    return api.get('/virtualization/overview')
  },
  filters() {
    return api.get('/virtualization/filters')
  },
  vms(params = {}) {
    return api.get('/virtualization/vms', { params })
  },
  vm(id) {
    return api.get(`/virtualization/vms/${id}`)
  },
  hosts(params = {}) {
    return api.get('/virtualization/hosts', { params })
  },
  host(id) {
    return api.get(`/virtualization/hosts/${id}`)
  },
  top(metric, limit = 10, platformId = null, target = 'vm') {
    return api.get('/virtualization/top', { params: { metric, limit, platform_id: platformId || undefined, target } })
  },
  alertSettings() {
    return api.get('/virtualization/alert-settings')
  },
  saveAlertSettings(data) {
    return api.put('/virtualization/alert-settings', data)
  },
  vmAlerts(params = {}) {
    return api.get('/virtualization/vm-alerts', { params })
  },
  acknowledgeVmAlert(alertId, data = {}) {
    return api.post(`/virtualization/vm-alerts/${alertId}/ack`, data)
  },
  updateVmAlert(alertId, data) {
    return api.put(`/virtualization/vm-alerts/${alertId}`, data)
  },
  bulkAcknowledgeVmAlerts(ids, data = {}) {
    return api.post('/virtualization/vm-alerts/bulk-ack', { ids, ...data })
  },
  deleteVmAlert(alertId) {
    return api.delete(`/virtualization/vm-alerts/${alertId}`)
  },
  bulkDeleteVmAlerts(ids) {
    return api.post('/virtualization/vm-alerts/bulk-delete', { ids })
  },
}

// 即时通信 / 悬浮球个人偏好
export const imApi = {
  webrtcConfig() {
    return api.get('/im/webrtc-config')
  },
  users() {
    return api.get('/im/users')
  },
  messages(peerId, limit = 100) {
    return api.get(`/im/messages/${peerId}`, { params: { limit } })
  },
  recallMessage(messageId) {
    return api.post(`/im/messages/${messageId}/recall`)
  },
  deleteMessage(messageId) {
    return api.delete(`/im/messages/${messageId}`)
  },
  unread() {
    return api.get('/im/unread')
  },
  preferences() {
    return api.get('/im/preferences')
  },
  savePreferences(settings) {
    return api.put('/im/preferences', { settings })
  },
  uploadAttachment(file, onProgress) {
    const form = new FormData()
    form.append('file', file)
    return api.post('/im/upload', form, {
      timeout: 0,
      onUploadProgress: (event) => {
        if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100))
      },
    })
  },
  // ---- 群组 ----
  groups() {
    return api.get('/im/groups')
  },
  createGroup(payload) {
    return api.post('/im/groups', payload)
  },
  group(groupId) {
    return api.get(`/im/groups/${groupId}`)
  },
  groupMessages(groupId, limit = 100) {
    return api.get(`/im/groups/${groupId}/messages`, { params: { limit } })
  },
  groupMembers(groupId) {
    return api.get(`/im/groups/${groupId}/members`)
  },
  addGroupMembers(groupId, userIds) {
    return api.post(`/im/groups/${groupId}/members`, { user_ids: userIds })
  },
  removeGroupMember(groupId, userId) {
    return api.delete(`/im/groups/${groupId}/members/${userId}`)
  },
  leaveGroup(groupId) {
    return api.post(`/im/groups/${groupId}/leave`)
  },
  groupWhiteboard(groupId, limit = 500) {
    return api.get(`/im/groups/${groupId}/whiteboard`, { params: { limit } })
  },
  attachmentUrl(id) {
    return `/api/im/files/${id}?token=${encodeURIComponent(getToken())}`
  },
}

export default api


// AI智能运维
export const aiApi = {
  status() { return api.get('/ai/status') },
  overview() { return api.get('/ai/overview') },
  chat(data) { return api.post('/ai/chat', data, { timeout: 90000 }) },
  agentChat(data, config = {}) { return api.post('/ai/agent/chat', data, { timeout: 180000, ...config }) },
  agentCapabilities() { return api.get('/ai/agent/capabilities') },
  resetChat(data = {}) { return api.post('/ai/chat/reset', data) },
  alertAnalysis() { return api.get('/ai/alerts/analysis') },
  getConfig() { return api.get('/ai/config') },
  saveConfig(data) { return api.put('/ai/config', data) },
  testConfig(data = {}) { return api.post('/ai/config/test', data, { timeout: 90000 }) },
  tts(data) { return api.post('/ai/tts', data, { responseType: 'blob', timeout: 90000 }) },
  generateReport(data) { return api.post('/ai/reports', data, { timeout: 120000 }) },
  reports(params) { return api.get('/ai/reports', { params }) },
  downloadUrl(id) { return `/api/ai/reports/${id}/download` },
}


// 总部分支级联
export const cascadeApi = {
  status() { return api.get('/cascade/status') },
  getConfig() { return api.get('/cascade/config') },
  saveConfig(data) { return api.put('/cascade/config', data) },
  nodes() { return api.get('/cascade/nodes') },
  createNode(data) { return api.post('/cascade/nodes', data) },
  getNode(id) { return api.get(`/cascade/nodes/${id}`) },
  deleteNode(id) { return api.delete(`/cascade/nodes/${id}`) },
  messages(params) { return api.get('/cascade/messages', { params }) },
  sendMessage(data) { return api.post('/cascade/messages', data) },
}
