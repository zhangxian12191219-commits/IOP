/**
 * 响应时间显示：保留亚毫秒精度，避免 0.126ms 被 toFixed(0) 显示成 0ms。
 */
export function formatLatency(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return '-'
  if (number < 0.01) return '<0.01ms'
  if (number < 1) return `${number.toFixed(2)}ms`
  if (number < 10) return `${number.toFixed(1)}ms`
  return `${number.toFixed(0)}ms`
}
