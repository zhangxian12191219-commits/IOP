<template>
  <div class="vz-chart" :class="tone">
    <svg viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="color" stop-opacity="0.36" />
          <stop offset="100%" :stop-color="color" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path :d="areaPath" :fill="`url(#${gradientId})`" />
      <path :d="linePath" class="vz-chart-line" :stroke="color" />
      <path :d="linePath" class="vz-chart-scan" :stroke="color" />
      <circle :cx="last.x" :cy="last.y" r="1.8" :fill="color" class="vz-chart-dot" />
    </svg>
    <span class="vz-chart-glow" :style="{ background: color }"></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  tone: { type: String, default: 'cyan' },
  seed: { type: Number, default: 1 },
})

const colors = {
  cyan: '#38bdf8',
  blue: '#60a5fa',
  violet: '#a78bfa',
  emerald: '#34d399',
  amber: '#fbbf24',
  rose: '#fb7185',
  slate: '#94a3b8',
}
const color = computed(() => colors[props.tone] || colors.cyan)
const gradientId = `vz-chart-${Math.random().toString(16).slice(2)}`

const points = computed(() => {
  const base = Math.max(4, Math.min(100, Number(props.value) || 0))
  const total = 22
  return Array.from({ length: total }, (_, index) => {
    const phase = (index / (total - 1)) * Math.PI * 2
    const wobble = Math.sin(phase * 1.35 + props.seed) * 8 + Math.cos(phase * 2.2 - props.seed) * 4
    const trend = (index / (total - 1) - 0.5) * 8
    const value = Math.max(3, Math.min(31, 30 - (base * 0.25) + wobble + trend))
    return { x: (index / (total - 1)) * 100, y: value }
  })
})

const linePath = computed(() => points.value.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' '))
const areaPath = computed(() => `${linePath.value} L100 34 L0 34 Z`)
const last = computed(() => points.value[points.value.length - 1])
</script>

<style scoped>
.vz-chart {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 24px;
  overflow: hidden;
  opacity: 0.9;
}

.vz-chart svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.vz-chart-line {
  fill: none;
  stroke-width: 1.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  filter: drop-shadow(0 0 3px currentColor);
  stroke-dasharray: 170;
  stroke-dashoffset: 170;
  animation: vz-chart-draw 2.4s ease forwards, vz-chart-breathe 3.6s ease-in-out 2.4s infinite;
}

.vz-chart-scan {
  fill: none;
  stroke-width: 2.2;
  stroke-linecap: round;
  opacity: 0.18;
  stroke-dasharray: 9 160;
  animation: vz-chart-scan 3.8s linear infinite;
}

.vz-chart-dot {
  filter: drop-shadow(0 0 4px currentColor);
  animation: vz-chart-dot 1.8s ease-in-out infinite;
}

.vz-chart-glow {
  position: absolute;
  right: 8%;
  bottom: -16px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  opacity: 0.12;
  filter: blur(10px);
}

@keyframes vz-chart-draw {
  to { stroke-dashoffset: 0; }
}

@keyframes vz-chart-breathe {
  0%, 100% { opacity: 0.72; }
  50% { opacity: 1; }
}

@keyframes vz-chart-scan {
  from { stroke-dashoffset: 170; }
  to { stroke-dashoffset: -20; }
}

@keyframes vz-chart-dot {
  0%, 100% { opacity: 0.5; r: 1.4; }
  50% { opacity: 1; r: 2.2; }
}
</style>
