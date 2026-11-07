// 服务器温度探头的显示名称。保留原始 name 用于采集匹配，只在展示层做本地化。
const EXACT_LABELS = [
  [/^system\s+board\s+inlet\s+temp(erature)?$/i, '系统板入口温度'],
  [/^system\s+board\s+intake\s+temp(erature)?$/i, '系统板入口温度'],
  [/^system\s+board\s+exhaust\s+temp(erature)?$/i, '系统板排气温度'],
  [/^system\s+board\s+outlet\s+temp(erature)?$/i, '系统板排气温度'],
  [/^system\s+board\s+temp(erature)?$/i, '系统板温度'],
  [/^inlet\s+temp(erature)?$/i, '进风温度'],
  [/^intake\s+temp(erature)?$/i, '进风温度'],
  [/^outlet\s+temp(erature)?$/i, '排风温度'],
  [/^exhaust\s+temp(erature)?$/i, '排风温度'],
  [/^ambient\s+temp(erature)?$/i, '环境温度'],
  [/^pch\s+temp(erature)?$/i, 'PCH 温度'],
  [/^raid\s+temp(erature)?$/i, 'RAID 温度'],
]

export function temperatureDisplayName(name, fallback = '温度') {
  const raw = String(name || '').trim()
  if (!raw) return fallback
  for (const [pattern, label] of EXACT_LABELS) {
    if (pattern.test(raw)) return label
  }
  const cpuMatch = raw.match(/^cpu\s*(\d+)\s+(core\s+rem|mem|vddq|vrd)\s+temp(erature)?$/i)
  if (cpuMatch) {
    const suffix = { 'core rem': '核心温度', mem: '内存温度', vddq: 'VDDQ 温度', vrd: 'VRD 温度' }[cpuMatch[2].toLowerCase()]
    return `CPU${cpuMatch[1]} ${suffix}`
  }
  if (/^rear\s*disk\s*(\d+)\s+temp(erature)?$/i.test(raw)) {
    return raw.replace(/^rear\s*disk\s*(\d+)\s+temp(erature)?$/i, '后置硬盘$1温度')
  }
  if (/\btemp(erature)?$/i.test(raw)) {
    return `${raw.replace(/\s*temp(erature)?$/i, '').trim()} 温度`
  }
  return raw
}
