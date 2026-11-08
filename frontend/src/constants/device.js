/**
 * 设备类型统一定义
 *
 * 全站（总览、资产列表、设备表单、设备详情、大屏、拓扑）共用一套：
 * 唯一 value、名称（随语言切换）、标签颜色、图表颜色，避免各处映射不一致。
 */
import { t } from '@/i18n'

export const DEVICE_TYPES = [
  { value: 'router', get label() { return t('device.type.router') }, tagType: 'primary', color: '#1890ff' },
  { value: 'switch', get label() { return t('device.type.switch') }, tagType: 'success', color: '#52c41a' },
  { value: 'firewall', get label() { return t('device.type.firewall') }, tagType: 'danger', color: '#f5222d' },
  { value: 'security', get label() { return t('device.type.security') }, tagType: 'warning', color: '#fa8c16' },
  { value: 'wireless', get label() { return t('device.type.wireless') }, tagType: 'success', color: '#13c2c2' },
  { value: 'loadbalancer', get label() { return t('device.type.loadbalancer') }, tagType: 'primary', color: '#2f54eb' },
  { value: 'storage', get label() { return t('device.type.storage') }, tagType: 'info', color: '#595959' },
  { value: 'server', get label() { return t('device.type.server') }, tagType: 'info', color: '#722ed1' },
  { value: 'camera', get label() { return t('device.type.camera') }, tagType: 'warning', color: '#08979c' },
  { value: 'printer', get label() { return t('device.type.printer') }, tagType: 'info', color: '#eb2f96' },
  { value: 'ups', get label() { return t('device.type.ups') }, tagType: 'info', color: '#d48806' },
  { value: 'pc', get label() { return t('device.type.pc') }, tagType: 'info', color: '#fa8c16' },
  { value: 'other', get label() { return t('device.type.other') }, tagType: 'info', color: '#8c8c8c' },
]

// 拓扑专用虚拟类型：不会出现在资产类型下拉中，仅用于拓扑标签/颜色
const CLOUD_VIRTUAL_TYPE = {
  value: 'cloud',
  label: '云 / 互联网出口',
  tagType: 'primary',
  color: '#0ea5e9',
}

const DEVICE_TYPE_MAP = Object.fromEntries(DEVICE_TYPES.map((item) => [item.value, item]))

const UNKNOWN = { value: 'other', get label() { return t('device.type.other') }, tagType: 'info', color: '#8c8c8c' }

/** 常见厂商（可下拉选择，也允许直接输入自定义厂商） */
export const VENDOR_OPTIONS = [
  'Huawei', 'Cisco', 'H3C', 'Ruijie', 'Fortinet', 'Hillstone',
  'Sangfor', 'Topsec', 'Juniper', 'Arista', 'TP-Link', 'MikroTik', 'Ubiquiti', 'F5', 'A10',
  'Hikvision', 'Dahua', 'ZTE', 'Maipu', 'Dell', 'HP', 'Lenovo', 'Inspur',
  'IBM', 'VMware', 'Microsoft', 'Apple', 'Samsung', 'Netgear', 'D-Link',
]

/** 资产表单/筛选可选的类型（也允许用户输入自定义类型） */
export const SELECTABLE_DEVICE_TYPES = DEVICE_TYPES

export function deviceTypeMeta(value) {
  if (!value) return UNKNOWN
  if (value === CLOUD_VIRTUAL_TYPE.value) return CLOUD_VIRTUAL_TYPE
  const known = DEVICE_TYPE_MAP[value]
  if (known) return known
  // 自定义类型：直接显示用户录入的类型名
  return {
    value,
    get label() { return value },
    tagType: 'info',
    color: '#8c8c8c',
  }
}

export function deviceTypeLabel(value) {
  return deviceTypeMeta(value).label
}

export function deviceTypeTagType(value) {
  return deviceTypeMeta(value).tagType
}

export function deviceTypeColor(value) {
  return deviceTypeMeta(value).color
}

/** 可选项（el-select / el-option），label 随当前语言动态取值 */
export const DEVICE_TYPE_OPTIONS = SELECTABLE_DEVICE_TYPES.map((item) => ({
  value: item.value,
  get label() {
    return item.label
  },
}))
