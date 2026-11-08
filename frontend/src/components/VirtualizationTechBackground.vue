<template>
  <div class="vz-tech-bg" aria-hidden="true">
    <canvas ref="canvasRef" class="vz-tech-canvas"></canvas>
    <div class="vz-tech-overlay"></div>
    <div class="vz-tech-scan"></div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canvasRef = ref(null)
let ctx = null
let frame = null
let particles = []
let width = 0
let height = 0
let dpr = 1

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  dpr = Math.min(2, window.devicePixelRatio || 1)
  width = Math.max(1, rect.width)
  height = Math.max(1, rect.height)
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)
  ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  const count = Math.max(26, Math.min(72, Math.round((width * height) / 26000)))
  particles = Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.22,
    vy: (Math.random() - 0.5) * 0.22,
    r: Math.random() * 1.6 + 0.7,
    phase: Math.random() * Math.PI * 2,
  }))
}

function draw(time = 0) {
  frame = requestAnimationFrame(draw)
  if (!ctx) return
  ctx.clearRect(0, 0, width, height)
  const glow = ctx.createRadialGradient(width * 0.15, height * 0.1, 0, width * 0.15, height * 0.1, width * 0.65)
  glow.addColorStop(0, 'rgba(8, 145, 178, 0.11)')
  glow.addColorStop(0.55, 'rgba(14, 116, 144, 0.035)')
  glow.addColorStop(1, 'rgba(2, 8, 20, 0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, width, height)

  particles.forEach((particle, index) => {
    particle.x += particle.vx
    particle.y += particle.vy
    if (particle.x < -10) particle.x = width + 10
    if (particle.x > width + 10) particle.x = -10
    if (particle.y < -10) particle.y = height + 10
    if (particle.y > height + 10) particle.y = -10
    const pulse = 0.65 + Math.sin(time / 900 + particle.phase) * 0.3
    ctx.beginPath()
    ctx.fillStyle = `rgba(103, 232, 249, ${0.4 + pulse * 0.4})`
    ctx.shadowColor = 'rgba(34, 211, 238, 0.55)'
    ctx.shadowBlur = 8
    ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2)
    ctx.fill()
    ctx.shadowBlur = 0

    for (let next = index + 1; next < particles.length; next += 1) {
      const other = particles[next]
      const dx = particle.x - other.x
      const dy = particle.y - other.y
      const distance = Math.hypot(dx, dy)
      if (distance > 145) continue
      ctx.beginPath()
      ctx.strokeStyle = `rgba(56, 189, 248, ${(1 - distance / 145) * 0.18})`
      ctx.lineWidth = 0.65
      ctx.moveTo(particle.x, particle.y)
      ctx.lineTo(other.x, other.y)
      ctx.stroke()
    }
  })

  const scan = ((time / 45) % (height + 160)) - 80
  const scanGradient = ctx.createLinearGradient(0, scan - 32, 0, scan + 32)
  scanGradient.addColorStop(0, 'rgba(34, 211, 238, 0)')
  scanGradient.addColorStop(0.5, 'rgba(34, 211, 238, 0.045)')
  scanGradient.addColorStop(1, 'rgba(34, 211, 238, 0)')
  ctx.fillStyle = scanGradient
  ctx.fillRect(0, scan - 32, width, 64)
}

onMounted(() => {
  resize()
  window.addEventListener('resize', resize, { passive: true })
  frame = requestAnimationFrame(draw)
})

onBeforeUnmount(() => {
  if (frame) cancelAnimationFrame(frame)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.vz-tech-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.vz-tech-bg::before,
.vz-tech-bg::after {
  position: absolute;
  width: min(62vw, 860px);
  aspect-ratio: 1;
  border: 1px solid rgba(34, 211, 238, .14);
  border-radius: 50%;
  content: '';
  box-shadow: 0 0 60px rgba(34, 211, 238, .06), inset 0 0 60px rgba(34, 211, 238, .04);
}

.vz-tech-bg::before {
  left: -220px;
  bottom: -420px;
  animation: vzOrbit 34s linear infinite;
}

.vz-tech-bg::after {
  right: -260px;
  top: -430px;
  border-color: rgba(99, 102, 241, .16);
  animation: vzOrbitReverse 42s linear infinite;
}

.vz-tech-canvas {
  width: 100%;
  height: 100%;
  opacity: .95;
}

.vz-tech-overlay {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 13% 0%, rgba(34, 211, 238, .12), transparent 34%),
    radial-gradient(ellipse at 88% 100%, rgba(99, 102, 241, .14), transparent 38%),
    linear-gradient(180deg, rgba(2, 8, 20, .05), rgba(2, 8, 20, .28));
}

.vz-tech-scan {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(180deg, transparent 0, transparent 4px, rgba(56, 189, 248, .022) 5px);
  background-size: 100% 10px;
  mix-blend-mode: screen;
  animation: vzScanMove 9s linear infinite;
}

.vz-tech-scan::before {
  position: absolute;
  top: -10%;
  left: 15%;
  width: 70%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(34, 211, 238, .42), transparent);
  box-shadow: 0 0 18px rgba(34, 211, 238, .35);
  content: '';
  animation: vzBeamSweep 7s ease-in-out infinite;
}

@keyframes vzOrbit {
  from { transform: rotate(0deg) translateX(0); }
  to { transform: rotate(360deg) translateX(6px); }
}

@keyframes vzOrbitReverse {
  from { transform: rotate(360deg) translateX(0); }
  to { transform: rotate(0deg) translateX(-6px); }
}

@keyframes vzScanMove {
  from { background-position: 0 0; }
  to { background-position: 0 80px; }
}

@keyframes vzBeamSweep {
  0%, 100% { top: 12%; opacity: .15; }
  50% { top: 82%; opacity: .6; }
}

</style>
