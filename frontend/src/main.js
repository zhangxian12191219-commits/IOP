import { createApp, computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ElTable } from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import enUs from 'element-plus/es/locale/lang/en'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router/index.js'
import { locale } from '@/i18n'

// 全站启用表头列宽拖拽：Element Plus 仅在 border 模式下显示列宽调整手柄
if (ElTable?.props?.border) {
  ElTable.props.border = { type: Boolean, default: true }
}

// 表格列宽记忆：按页面路径+表格位置+列结构保存，返回页面时恢复
const TABLE_WIDTH_STORAGE_KEY = 'nms_table_column_widths_v1'
const originalTableSetup = ElTable?.setup

function tableWidthKey(el) {
  if (!el || typeof document === 'undefined') return ''
  const tables = [...document.querySelectorAll('.el-table')]
  const index = Math.max(0, tables.indexOf(el))
  const headers = [...el.querySelectorAll('.el-table__header th .cell')]
    .map((cell) => cell.textContent.trim())
    .join('|')
  return `${window.location.pathname}#${index}#${headers}`
}

function tableColumnWidths(instance) {
  const columns = instance?.exposed?.store?.states?.columns?.value || []
  return columns.map((column) => Math.round(Number(column.realWidth || column.width || 0)))
}

function restoreColumnWidths(instance) {
  const el = instance?.vnode?.el
  const columns = instance?.exposed?.store?.states?.columns?.value || []
  if (!el || !columns.length) return
  let all = {}
  try {
    all = JSON.parse(localStorage.getItem(TABLE_WIDTH_STORAGE_KEY) || '{}')
  } catch {
    return
  }
  const widths = all[tableWidthKey(el)]
  if (!Array.isArray(widths) || widths.length !== columns.length) return
  let changed = false
  columns.forEach((column, index) => {
    const width = Number(widths[index])
    if (Number.isFinite(width) && width >= 40) {
      column.width = width
      if (Number(column.minWidth || 0) > width) column.minWidth = width
      changed = true
    }
  })
  if (changed) {
    instance.exposed?.doLayout?.()
  }
}

function persistColumnWidths(instance) {
  const el = instance?.vnode?.el
  const widths = tableColumnWidths(instance)
  if (!el || !widths.length) return
  try {
    let all = {}
    try {
      all = JSON.parse(localStorage.getItem(TABLE_WIDTH_STORAGE_KEY) || '{}')
    } catch {
      all = {}
    }
    all[tableWidthKey(el)] = widths
    localStorage.setItem(TABLE_WIDTH_STORAGE_KEY, JSON.stringify(all))
  } catch {
    /* 忽略存储异常 */
  }
}

if (typeof originalTableSetup === 'function' && !originalTableSetup.__dshColumnWidthPatched) {
  ElTable.setup = function patchedTableSetup(props, context) {
    const result = originalTableSetup.call(this, props, context)
    const instance = getCurrentInstance()
    if (instance) {
      let lastWidths = []
      let saveTimer = null
      let ownerDocument = null
      const tableEl = () => instance.vnode.el
      const onMouseUp = () => {
        clearTimeout(saveTimer)
        saveTimer = setTimeout(() => {
          const widths = tableColumnWidths(instance)
          if (!widths.length) return
          if (lastWidths.length && widths.some((width, index) => width !== lastWidths[index])) {
            persistColumnWidths(instance)
          }
          lastWidths = widths
        }, 50)
      }
      onMounted(async () => {
        await nextTick()
        ownerDocument = tableEl()?.ownerDocument || document
        setTimeout(() => {
          restoreColumnWidths(instance)
          lastWidths = tableColumnWidths(instance)
          ownerDocument.addEventListener('mouseup', onMouseUp, true)
        }, 50)
      })
      onBeforeUnmount(() => {
        clearTimeout(saveTimer)
        ownerDocument?.removeEventListener('mouseup', onMouseUp, true)
      })
    }
    return result
  }
  ElTable.setup.__dshColumnWidthPatched = true
}

const app = createApp(App)
const pinia = createPinia()

// 注册 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(pinia)
app.use(router)
// 全局注入响应式的 Element Plus locale：
// - 模板组件由 App.vue 的 <el-config-provider> 提供
// - 命令式服务（ElMessageBox 等）走 app 级全局配置，需同一份响应式 locale
app.use(
  ElementPlus,
  computed(() => ({
    locale: locale.value === 'en-US' ? enUs : zhCn,
  }))
)

app.mount('#app')
