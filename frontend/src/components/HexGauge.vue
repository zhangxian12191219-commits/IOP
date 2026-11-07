<template>
  <div
    class="hex-cell sphere-gauge"
    :class="[severity, { fluid, 'has-graphic': graphic }]"
    :style="{
      '--hex-color': color,
      '--level': safePercent,
      '--fill': `${safePercent}%`,
      '--hex-font-scale': fontScale,
    }"
    :title="`${deviceName} · ${metricLabel} · ${displayValue}${unit}`"
  >
    <div v-if="graphic" class="metric-graphic-shell" :class="`graphic-${graphic}`">
      <div class="graphic-halo"></div>
      <svg class="graphic-icon" viewBox="0 0 64 64" aria-hidden="true">
        <g v-if="graphic === 'cpu'">
          <rect class="line" x="16" y="16" width="32" height="32" rx="5" />
          <rect class="solid-soft" x="24" y="24" width="16" height="16" rx="3" />
          <path class="line" d="M24 8v8M32 8v8M40 8v8M24 48v8M32 48v8M40 48v8M8 24h8M8 32h8M8 40h8M48 24h8M48 32h8M48 40h8" />
        </g>
        <g v-else-if="graphic === 'memory'">
          <rect class="line" x="9" y="19" width="46" height="25" rx="4" />
          <path class="line" d="M18 19v25M27 19v25M36 19v25M45 19v25M18 44v6M26 44v6M34 44v6M42 44v6M50 44v6" />
          <rect class="solid-soft" x="21" y="24" width="5" height="15" rx="1" />
          <rect class="solid-soft" x="30" y="24" width="5" height="15" rx="1" />
          <rect class="solid-soft" x="39" y="24" width="5" height="15" rx="1" />
        </g>
        <g v-else-if="graphic === 'fan'">
          <g class="fan-blades">
            <path class="solid-soft" d="M32 27c-4-10-13-13-17-8-4 5 3 13 11 15z" />
            <path class="solid-soft" d="M37 32c10-4 13-13 8-17-5-4-13 3-15 11z" />
            <path class="solid-soft" d="M32 37c4 10 13 13 17 8 4-5-3-13-11-15z" />
            <path class="solid-soft" d="M27 32c-10 4-13 13-8 17 5 4 13-3 15-11z" />
          </g>
          <circle class="line" cx="32" cy="32" r="6" />
          <circle class="solid" cx="32" cy="32" r="2.4" />
        </g>
        <g v-else-if="graphic === 'temperature'">
          <path class="line" d="M36 13a4 4 0 0 0-8 0v22a9 9 0 1 0 8 0z" />
          <path class="line" d="M32 20v21" />
          <circle class="solid-soft" cx="32" cy="47" r="5" />
          <path class="line" d="M42 18h7M42 25h5M42 32h7M42 39h5" />
        </g>
        <g v-else-if="graphic === 'power'">
          <path class="solid-soft" d="M36 5 17 35h12l-2 24 20-32H34z" />
          <path class="line" d="M32 14v8M27 45h10" />
        </g>
        <g v-else-if="graphic === 'disk'">
          <rect class="line" x="9" y="15" width="46" height="34" rx="7" />
          <circle class="line" cx="24" cy="32" r="8" />
          <path class="line" d="M24 24a8 8 0 0 1 8 8M24 24v16M38 25h10M38 32h10M38 39h8" />
          <circle class="solid" cx="24" cy="32" r="2" />
        </g>
        <g v-else-if="graphic === 'network'">
          <circle class="line" cx="14" cy="16" r="5" />
          <circle class="line" cx="50" cy="16" r="5" />
          <circle class="line" cx="32" cy="48" r="5" />
          <path class="line" d="M19 16h26M14 21v15a7 7 0 0 0 7 7h6M50 21v15a7 7 0 0 1-7 7h-6" />
          <circle class="solid" cx="14" cy="16" r="1.8" />
          <circle class="solid" cx="50" cy="16" r="1.8" />
          <circle class="solid" cx="32" cy="48" r="1.8" />
        </g>
      </svg>
      <div class="graphic-content">
        <span class="graphic-label">{{ metricLabel }}</span>
        <strong class="graphic-value">{{ displayValue }}<small v-if="unit">{{ unit }}</small></strong>
        <span class="hex-status graphic-status"><i :class="{ alert: statusAlert }"></i>{{ statusText }}</span>
      </div>
    </div>
    <template v-else>
    <div class="sphere-halo"></div>
    <div class="sphere-shell">
      <div class="sphere-water">
        <div class="wave wave-back" aria-hidden="true">
          <svg viewBox="0 0 240 24" preserveAspectRatio="none">
            <path d="M0 12 Q 15 4 30 12 T 60 12 T 90 12 T 120 12 T 150 12 T 180 12 T 210 12 T 240 12 V24 H0 Z" />
          </svg>
        </div>
        <div class="wave wave-front" aria-hidden="true">
          <svg viewBox="0 0 240 24" preserveAspectRatio="none">
            <path d="M0 12 Q 15 4 30 12 T 60 12 T 90 12 T 120 12 T 150 12 T 180 12 T 210 12 T 240 12 V24 H0 Z" />
          </svg>
        </div>
        <span class="bubble bubble-a"></span>
        <span class="bubble bubble-b"></span>
        <span class="bubble bubble-c"></span>
        <span class="bubble bubble-d"></span>
      </div>
      <div class="sphere-shine"></div>
      <div class="hex-content">
        <span class="hex-metric hex-metric-top">{{ metricLabel }}</span>
        <strong class="hex-value">
          {{ displayValue }}<small v-if="unit">{{ unit }}</small>
        </strong>
        <span class="hex-status"><i :class="{ alert: statusAlert }"></i>{{ statusText }}</span>
      </div>
    </div>
    <div class="sphere-ring"></div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  deviceName: { type: String, default: '' },
  metricLabel: { type: String, default: '' },
  displayValue: { type: String, default: '--' },
  unit: { type: String, default: '' },
  percent: { type: Number, default: 0 },
  color: { type: String, default: '#38bdf8' },
  statusText: { type: String, default: '在线' },
  statusAlert: { type: Boolean, default: false },
  severity: { type: String, default: 'normal' },
  fluid: { type: Boolean, default: false },
  fontScale: { type: Number, default: 1 },
  graphic: { type: String, default: '' },
})

const safePercent = computed(() => {
  const value = Number(props.percent)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value))
})

const fontScale = computed(() => {
  const value = Number(props.fontScale)
  if (!Number.isFinite(value)) return 1
  return Math.max(0.1, Math.min(1.5, value))
})
</script>

<style scoped>
.hex-cell {
  position: relative;
  width: var(--hex-width, 152px);
  height: var(--hex-width, 152px);
  flex-shrink: 0;
  cursor: pointer;
  transition: transform 0.28s ease, filter 0.28s ease;
}

.hex-cell:hover {
  transform: translateY(-4px) scale(1.015);
  filter: brightness(1.1);
}

.hex-cell.fluid {
  width: 100%;
  height: auto;
  max-width: none;
  aspect-ratio: 1 / 1;
}

.hex-cell.has-graphic {
  container-type: inline-size;
}

.metric-graphic-shell {
  position: absolute;
  inset: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1.5%;
  padding: 9% 8% 8%;
  border: 1px solid color-mix(in srgb, var(--hex-color) 46%, rgba(148, 163, 184, 0.2));
  border-radius: 50%;
  background:
    radial-gradient(circle at 34% 22%, rgba(255, 255, 255, 0.08), transparent 34%),
    radial-gradient(circle at 50% 110%, color-mix(in srgb, var(--hex-color) 20%, transparent), transparent 60%),
    linear-gradient(155deg, #0b1d31 0%, #050e1b 72%);
  box-shadow:
    inset 0 0 28px rgba(1, 10, 20, 0.9),
    inset 0 1px 1px rgba(255, 255, 255, 0.1),
    0 10px 26px rgba(1, 10, 20, 0.38),
    0 0 24px color-mix(in srgb, var(--hex-color) 18%, transparent);
}

.metric-graphic-shell::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(
    var(--hex-color) calc(var(--level) * 1%),
    rgba(148, 163, 184, 0.1) 0
  );
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 5px), #000 calc(100% - 4px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 5px), #000 calc(100% - 4px));
  opacity: 0.85;
  pointer-events: none;
}

.graphic-halo {
  position: absolute;
  inset: 14%;
  border-radius: 50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--hex-color) 38%, transparent), transparent 68%);
  filter: blur(14px);
  opacity: 0.32;
  pointer-events: none;
}

.graphic-icon {
  position: relative;
  z-index: 2;
  width: 44%;
  height: 38%;
  min-width: 22px;
  min-height: 20px;
  max-width: 110px;
  max-height: 92px;
  flex: 0 0 auto;
  color: var(--hex-color);
  filter: drop-shadow(0 0 9px color-mix(in srgb, var(--hex-color) 55%, transparent));
}

.graphic-icon .line {
  fill: none;
  stroke: currentColor;
  stroke-width: 2.3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.graphic-icon .solid {
  fill: currentColor;
  stroke: none;
}

.graphic-icon .solid-soft {
  fill: currentColor;
  stroke: currentColor;
  stroke-width: 0.8;
  opacity: 0.32;
}

.graphic-content {
  position: relative;
  z-index: 2;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  text-align: center;
}

.graphic-label {
  max-width: 100%;
  overflow: hidden;
  color: #c8e4f4;
  font-family: -apple-system, 'Microsoft YaHei', sans-serif;
  font-size: calc(clamp(7px, 4.2cqw, 12px) * var(--hex-font-scale, 1));
  font-weight: 600;
  letter-spacing: 0.2px;
  line-height: 1.2;
  text-overflow: ellipsis;
  text-shadow: 0 1px 5px rgba(0, 0, 0, 0.6);
  white-space: nowrap;
}

.graphic-value {
  max-width: 100%;
  overflow: hidden;
  color: #f0f9ff;
  font-family: Rajdhani, 'DIN Alternate', Consolas, monospace;
  font-size: calc(clamp(12px, 10cqw, 32px) * var(--hex-font-scale, 1));
  font-weight: 800;
  line-height: 1;
  letter-spacing: 0.2px;
  text-overflow: ellipsis;
  text-shadow: 0 0 18px color-mix(in srgb, var(--hex-color) 60%, transparent), 0 2px 8px rgba(0, 0, 0, 0.65);
  white-space: nowrap;
}

.graphic-value small {
  margin-left: 2px;
  color: #c5f0ff;
  font-family: Consolas, monospace;
  font-size: calc(clamp(6px, 4cqw, 10px) * var(--hex-font-scale, 1));
  font-weight: 400;
}

.graphic-status {
  margin-top: 1px;
  padding: 1px 5px;
  font-size: calc(clamp(6px, 3.2cqw, 8px) * var(--hex-font-scale, 1));
}

.graphic-fan .fan-blades {
  transform-origin: 32px 32px;
  animation: graphic-fan-spin 3.2s linear infinite;
}

.graphic-fan .solid-soft {
  opacity: 0.5;
}

.graphic-power .solid-soft {
  opacity: 0.45;
}

.hex-cell.warning .graphic-halo {
  animation: sphere-warning-pulse 2.8s ease-in-out infinite;
}

.hex-cell.critical .graphic-halo {
  animation: sphere-critical-pulse 1.8s ease-in-out infinite;
}

@keyframes graphic-fan-spin {
  to { transform: rotate(360deg); }
}

@container (max-width: 110px) {
  .graphic-icon {
    width: 34%;
    height: 30%;
    min-width: 18px;
    min-height: 16px;
  }

  .graphic-status {
    display: none;
  }

  .graphic-label {
    font-size: calc(clamp(6px, 4.2cqw, 8px) * var(--hex-font-scale, 1));
  }

  .graphic-value {
    font-size: calc(clamp(10px, 10cqw, 13px) * var(--hex-font-scale, 1));
  }
}

.sphere-halo {
  position: absolute;
  inset: 9%;
  border-radius: 50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--hex-color) 42%, transparent), transparent 68%);
  filter: blur(16px);
  opacity: 0.36;
  pointer-events: none;
}

.sphere-shell {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--hex-color) 48%, rgba(148, 163, 184, 0.2));
  border-radius: 50%;
  background:
    radial-gradient(circle at 34% 24%, rgba(255, 255, 255, 0.09), transparent 34%),
    radial-gradient(circle at 50% 112%, color-mix(in srgb, var(--hex-color) 16%, transparent), transparent 58%),
    linear-gradient(155deg, #0b1d31 0%, #050e1b 72%);
  box-shadow:
    inset 0 0 32px rgba(1, 10, 20, 0.9),
    inset 0 1px 1px rgba(255, 255, 255, 0.12),
    0 10px 26px rgba(1, 10, 20, 0.38),
    0 0 24px color-mix(in srgb, var(--hex-color) 18%, transparent);
}

.sphere-water {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: var(--fill);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--hex-color) 48%, transparent),
    color-mix(in srgb, var(--hex-color) 68%, #04111f) 70%,
    color-mix(in srgb, var(--hex-color) 78%, #020b15)
  );
  opacity: 0.82;
  transition: height 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}

.sphere-water::after {
  content: '';
  position: absolute;
  right: 8%;
  bottom: 5%;
  left: 8%;
  height: 26%;
  border-radius: 50%;
  background: radial-gradient(ellipse, rgba(255, 255, 255, 0.1), transparent 70%);
  pointer-events: none;
}

.wave {
  position: absolute;
  top: -9px;
  left: 0;
  width: 200%;
  height: 22px;
  color: color-mix(in srgb, var(--hex-color) 76%, #ffffff);
  animation: wave-shift 6.5s linear infinite;
}

.wave svg {
  display: block;
  width: 100%;
  height: 100%;
  fill: currentColor;
}

.wave-back {
  top: -7px;
  opacity: 0.34;
  animation-duration: 9s;
  animation-direction: reverse;
}

.wave-front {
  opacity: 0.7;
  animation-duration: 6.5s;
}

@keyframes wave-shift {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}

.bubble {
  position: absolute;
  bottom: 5%;
  display: block;
  width: 5px;
  height: 5px;
  border: 1px solid rgba(255, 255, 255, 0.38);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  opacity: 0;
  animation: bubble-rise 5.5s ease-in infinite;
}

.bubble-a {
  left: 27%;
  animation-delay: 0.8s;
}

.bubble-b {
  left: 57%;
  width: 4px;
  height: 4px;
  animation-delay: 2.2s;
  animation-duration: 6.8s;
}

.bubble-c {
  left: 73%;
  width: 3px;
  height: 3px;
  animation-delay: 1.5s;
  animation-duration: 7.5s;
}

.bubble-d {
  left: 42%;
  width: 3px;
  height: 3px;
  animation-delay: 3.6s;
  animation-duration: 4.8s;
}

@keyframes bubble-rise {
  0% { transform: translateY(0) scale(0.8); opacity: 0; }
  18% { opacity: 0.6; }
  75% { opacity: 0.35; }
  100% { transform: translateY(-128px) scale(1.15); opacity: 0; }
}

.sphere-shine {
  position: absolute;
  inset: 0;
  z-index: 2;
  border-radius: 50%;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.1), transparent 26%, transparent 70%, rgba(56, 189, 248, 0.05)),
    radial-gradient(circle at 50% 118%, transparent 58%, rgba(2, 10, 20, 0.5));
  pointer-events: none;
}

.sphere-ring {
  position: absolute;
  inset: -3px;
  z-index: 4;
  border-radius: 50%;
  background: conic-gradient(
    from -90deg,
    var(--hex-color) calc(var(--level) * 1%),
    rgba(148, 163, 184, 0.16) 0
  );
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 3px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 3px));
  opacity: 0.92;
  pointer-events: none;
}

.hex-content {
  position: relative;
  z-index: 3;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 2px;
  padding: 10% 12% 0;
  text-align: center;
}

.hex-metric {
  color: #b3d3e5;
  font-family: Consolas, monospace;
  font-size: calc(9px * var(--hex-font-scale, 1));
  letter-spacing: 0.5px;
  text-shadow: 0 1px 5px rgba(0, 0, 0, 0.6);
}

.hex-metric-top {
  max-width: 100%;
  overflow: hidden;
  color: #c8e4f4;
  font-family: -apple-system, 'Microsoft YaHei', sans-serif;
  font-size: calc(11px * var(--hex-font-scale, 1));
  font-weight: 600;
  letter-spacing: 0.2px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hex-value {
  color: #f0f9ff;
  font-family: Rajdhani, 'DIN Alternate', Consolas, monospace;
  font-size: calc(30px * var(--hex-font-scale, 1));
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: 0.3px;
  text-shadow: 0 0 22px color-mix(in srgb, var(--hex-color) 62%, transparent), 0 2px 10px rgba(0, 0, 0, 0.6);
  white-space: nowrap;
}

.hex-value small {
  margin-left: 2px;
  color: #c5f0ff;
  font-family: Consolas, monospace;
  font-size: calc(10px * var(--hex-font-scale, 1));
  font-weight: 400;
}

.hex-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
  padding: 2px 6px;
  border: 1px solid rgba(52, 211, 153, 0.2);
  border-radius: 9px;
  color: #6ee7b7;
  background: rgba(4, 26, 28, 0.45);
  font-size: calc(8px * var(--hex-font-scale, 1));
  line-height: 1.2;
  backdrop-filter: blur(3px);
}

.hex-cell.warning .hex-status {
  border-color: rgba(251, 191, 36, 0.22);
  color: #fbbf24;
  background: rgba(42, 30, 8, 0.48);
}

.hex-cell.critical .hex-status {
  border-color: rgba(251, 113, 133, 0.24);
  color: #fb7185;
  background: rgba(48, 14, 25, 0.5);
}

.hex-cell.muted .hex-status {
  border-color: rgba(148, 163, 184, 0.18);
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.45);
}

.hex-status i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 6px rgba(52, 211, 153, 0.85);
}

.hex-status i.alert {
  background: #fb7185;
  box-shadow: 0 0 6px rgba(251, 113, 133, 0.85);
}

.hex-cell.warning .sphere-halo {
  animation: sphere-warning-pulse 2.8s ease-in-out infinite;
}

.hex-cell.critical .sphere-halo {
  animation: sphere-critical-pulse 1.8s ease-in-out infinite;
}

@keyframes sphere-warning-pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.96); }
  50% { opacity: 0.6; transform: scale(1.03); }
}

@keyframes sphere-critical-pulse {
  0%, 100% { opacity: 0.36; transform: scale(0.96); }
  50% { opacity: 0.8; transform: scale(1.05); }
}

.hex-cell.fluid .hex-content {
  padding: 9% 12% 0;
  gap: 2px;
}

.hex-cell.fluid .hex-value {
  font-size: clamp(calc(24px * var(--hex-font-scale, 1)), calc(25cqw * var(--hex-font-scale, 1)), calc(46px * var(--hex-font-scale, 1)));
  font-weight: 800;
  letter-spacing: 0.2px;
}

.hex-cell.fluid .hex-value small {
  font-size: clamp(calc(7px * var(--hex-font-scale, 1)), calc(6cqw * var(--hex-font-scale, 1)), calc(10px * var(--hex-font-scale, 1)));
}

.hex-cell.fluid .hex-metric,
.hex-cell.fluid .hex-status {
  font-size: clamp(calc(6px * var(--hex-font-scale, 1)), calc(5.5cqw * var(--hex-font-scale, 1)), calc(9px * var(--hex-font-scale, 1)));
}

.hex-cell.fluid .hex-metric-top {
  font-size: clamp(calc(11px * var(--hex-font-scale, 1)), calc(8cqw * var(--hex-font-scale, 1)), calc(15px * var(--hex-font-scale, 1)));
  font-weight: 600;
}

@container (max-width: 110px) {
  .hex-cell.fluid .hex-content {
    padding: 7% 6% 0;
  }

  .hex-cell.fluid .hex-value {
    font-size: clamp(calc(16px * var(--hex-font-scale, 1)), calc(20cqw * var(--hex-font-scale, 1)), calc(24px * var(--hex-font-scale, 1)));
  }
}

@media (max-width: 1280px) {
  .hex-cell {
    --hex-width: 132px;
  }
}

@media (max-width: 760px) {
  .hex-cell {
    --hex-width: 116px;
  }

  .hex-value {
    font-size: calc(21px * var(--hex-font-scale, 1));
  }
}

@media (prefers-reduced-motion: reduce) {
  .wave,
  .bubble,
  .sphere-halo {
    animation: none !important;
  }

  .sphere-water {
    transition: none;
  }
}
</style>
