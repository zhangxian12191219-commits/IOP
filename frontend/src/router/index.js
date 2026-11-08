import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true, layout: 'blank' },
  },
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/instrument',
    name: 'InstrumentDashboard',
    component: () => import('@/views/InstrumentDashboard.vue'),
    meta: { title: '仪表盘', permission: 'monitor:view' },
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '监控总览', permission: 'monitor:view' },
  },
  {
    path: '/ai',
    name: 'AiOps',
    component: () => import('@/views/AiOpsView.vue'),
    meta: { title: 'AI智能运维', permission: 'ai:view' },
  },
  {
    path: '/ai-screen',
    name: 'AiOpsScreen',
    component: () => import('@/views/AiOpsScreen.vue'),
    meta: { title: 'AI运维大屏', layout: 'immersive', permission: 'ai:view' },
  },
  {
    path: '/cascade',
    name: 'Cascade',
    component: () => import('@/views/CascadeView.vue'),
    meta: { title: '级联管理', permission: 'cascade:view', requiresSuperuser: true },
  },
  {
    path: '/bigscreen',
    name: 'BigScreenManager',
    component: () => import('@/views/BigScreenManager.vue'),
    meta: { title: '大屏展示', permission: 'bigscreen:view' },
  },
  {
    path: '/bigscreen/ai',
    name: 'AiOpsBigScreen',
    component: () => import('@/views/AiOpsScreen.vue'),
    meta: { title: 'AI运维大屏', layout: 'immersive', permission: 'ai:view' },
  },
  {
    path: '/bigscreen/website',
    name: 'WebsiteBigScreen',
    component: () => import('@/views/WebsiteBigScreen.vue'),
    meta: { title: '网站监控大屏', layout: 'immersive', permission: 'website:view' },
  },
  {
    path: '/bigscreen/assets',
    name: 'AssetBigScreen',
    component: () => import('@/views/AssetBigScreen.vue'),
    meta: { title: '资产数字孪生大屏', layout: 'immersive', permission: 'bigscreen:view' },
  },
  {
    path: '/bigscreen/virtualization',
    name: 'VirtualizationBigScreen',
    component: () => import('@/views/VirtualizationBigScreen.vue'),
    meta: { title: '虚拟化资源大屏', layout: 'immersive', permission: 'virtualization:view' },
  },
  {
    path: '/bigscreen/view/:id',
    name: 'BigScreenView',
    component: () => import('@/views/BigScreenView.vue'),
    meta: { title: '大屏展示', layout: 'immersive', permission: 'bigscreen:view' },
  },
  // ===== 设备（资产管理）=====
  {
    path: '/devices',
    name: 'Devices',
    component: () => import('@/views/AssetList.vue'),
    meta: { title: '资产管理', permission: 'assets:view' },
  },
  {
    path: '/inspection',
    name: 'Inspection',
    component: () => import('@/views/InspectionView.vue'),
    meta: { title: '设备巡检', permission: 'inspection:view' },
  },
  {
    path: '/config-backups',
    name: 'ConfigBackups',
    component: () => import('@/views/ConfigBackupsView.vue'),
    meta: { title: '设备配置备份', permission: 'config_backup:view' },
  },
  {
    path: '/credentials',
    name: 'Credentials',
    component: () => import('@/views/CredentialsView.vue'),
    meta: { title: '设备凭据', permission: 'credentials:view' },
  },
  {
    path: '/discovery',
    name: 'Discovery',
    component: () => import('@/views/DiscoveryView.vue'),
    meta: { title: '自动发现', permission: 'discovery:view' },
  },
  {
    path: '/im',
    name: 'InstantMessaging',
    component: () => import('@/views/ImView.vue'),
    meta: { title: '即时通信' },
  },
  {
    path: '/tools',
    name: 'Tools',
    component: () => import('@/views/ToolsView.vue'),
    meta: { title: '系统工具', permission: 'tools:view' },
  },
  {
    path: '/devices/add',
    name: 'AddDevice',
    component: () => import('@/views/AssetForm.vue'),
    meta: { title: '添加设备', permission: 'assets:edit' },
  },
  {
    path: '/devices/edit/:id',
    name: 'EditDevice',
    component: () => import('@/views/AssetForm.vue'),
    meta: { title: '编辑设备', permission: 'assets:edit' },
  },
  {
    path: '/devices/copy/:id',
    name: 'CopyDevice',
    component: () => import('@/views/AssetForm.vue'),
    meta: { title: '复制设备', permission: 'assets:edit' },
  },
  {
    path: '/devices/:id',
    name: 'DeviceDetail',
    component: () => import('@/views/DeviceDetail.vue'),
    meta: { title: '设备详情', permission: 'assets:view' },
  },
  // 兼容旧链接
  { path: '/assets', redirect: '/devices' },
  { path: '/assets/add', redirect: '/devices/add' },
  { path: '/assets/edit/:id', redirect: (to) => `/devices/edit/${to.params.id}` },
  { path: '/assets/:id', redirect: (to) => `/devices/${to.params.id}` },

  {
    path: '/rooms',
    name: 'Rooms',
    component: () => import('@/views/RoomList.vue'),
    meta: { title: '机房管理', permission: 'rooms:view' },
  },
  {
    path: '/rooms/:id',
    redirect: (to) => `/rooms/${to.params.id}/showcase`,
  },
  {
    path: '/rooms/:id/showcase',
    name: 'RoomShowcase',
    component: () => import('@/views/RoomShowcase.vue'),
    meta: { title: '机房数字孪生', layout: 'immersive', permission: 'rooms:view' },
  },
  {
    path: '/mibs',
    name: 'Mibs',
    component: () => import('@/views/MibView.vue'),
    meta: { title: 'MIB 管理', permission: 'mib:view' },
  },
  {
    path: '/topology',
    name: 'Topology',
    component: () => import('@/views/TopologyView.vue'),
    meta: { title: '网络拓扑', permission: 'topology:view' },
  },
  {
    path: '/virtualization',
    name: 'Virtualization',
    component: () => import('@/views/VirtualizationView.vue'),
    meta: { title: '虚拟化管理', permission: 'virtualization:view' },
  },
  {
    path: '/website',
    name: 'WebsiteMonitor',
    component: () => import('@/views/WebsiteMonitor.vue'),
    meta: { title: '网站监控', permission: 'website:view' },
  },
  {
    path: '/website/certificates',
    name: 'WebsiteCertificates',
    component: () => import('@/views/CertificateView.vue'),
    meta: { title: '证书管理', permission: 'website:view' },
  },
  {
    path: '/website/add',
    name: 'AddWebsite',
    component: () => import('@/views/WebsiteForm.vue'),
    meta: { title: '添加网站监控', permission: 'website:edit' },
  },
  {
    path: '/website/edit/:id',
    name: 'EditWebsite',
    component: () => import('@/views/WebsiteForm.vue'),
    meta: { title: '编辑网站监控', permission: 'website:edit' },
  },
  {
    path: '/website/:id',
    name: 'WebsiteDetail',
    component: () => import('@/views/WebsiteDetail.vue'),
    meta: { title: '网站详情', permission: 'website:view' },
  },
  {
    path: '/alerts',
    name: 'Alerts',
    component: () => import('@/views/AlertsView.vue'),
    meta: { title: '告警中心', permission: 'monitor:view' },
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/views/NotificationsView.vue'),
    meta: { title: '告警渠道', permission: 'notifications:view', requiresSuperuser: true },
  },
  // ===== 系统管理 =====
  {
    path: '/system/users',
    redirect: () => ({ path: '/system/settings', query: { tab: 'users' } }),
    meta: { title: '用户权限', requiresSuperuser: true },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { title: '个人账户' },
  },
  {
    path: '/system/settings',
    name: 'SystemSettings',
    component: () => import('@/views/SystemSettings.vue'),
    meta: { title: '系统配置', permission: 'settings:view', requiresSuperuser: true },
  },
  {
    path: '/system/license',
    name: 'SystemLicense',
    component: () => import('@/views/LicenseView.vue'),
    meta: { title: '授权信息', permission: 'license:view', requiresSuperuser: true },
  },
  {
    path: '/system/audit',
    name: 'AuditLogs',
    component: () => import('@/views/AuditLogs.vue'),
    meta: { title: '审计日志', permission: 'audit:view' },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/** 前端路由守卫：未登录跳登录页；无权限跳首页 */
router.beforeEach((to) => {
  const token = localStorage.getItem('nms_token') || sessionStorage.getItem('nms_token')

  if (to.meta?.public) {
    if (token && to.path === '/login') return '/dashboard'
    return true
  }
  if (!token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  const need = to.meta?.permission
  if (need) {
    let user = null
    try {
      user = JSON.parse(
        localStorage.getItem('nms_user') || sessionStorage.getItem('nms_user') || 'null'
      )
    } catch {
      user = null
    }
    const allowed = user?.is_superuser || (user?.permissions || []).includes(need)
    // 没有任何监控权限的账号不要反复重定向到 /dashboard，直接进入个人账户
    if (!allowed) return to.path === '/dashboard' ? '/profile' : '/dashboard'
    if (to.meta?.requiresSuperuser && !user?.is_superuser) return '/profile'
  }
  return true
})

export default router
