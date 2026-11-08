<template>
  <div ref="hostRef" class="vz-scene">
    <canvas ref="canvasRef" class="vz-scene-canvas"></canvas>
    <div class="vz-scene-grid"></div>
    <div class="vz-cloud-art" aria-hidden="true">
      <svg viewBox="0 0 560 300" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="vz-cloud-white" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#ffffff" stop-opacity="0.98" />
            <stop offset="62%" stop-color="#f2fbff" stop-opacity="0.95" />
            <stop offset="100%" stop-color="#cfeeff" stop-opacity="0.86" />
          </linearGradient>
          <radialGradient id="vz-cloud-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#e0f7ff" stop-opacity="0.5" />
            <stop offset="100%" stop-color="#38bdf8" stop-opacity="0" />
          </radialGradient>
          <filter id="vz-cloud-soft" x="-20%" y="-30%" width="140%" height="170%">
            <feGaussianBlur stdDeviation="2.2" />
          </filter>
          <filter id="vz-cloud-shadow" x="-25%" y="-25%" width="150%" height="180%">
            <feGaussianBlur stdDeviation="12" />
          </filter>
        </defs>
        <ellipse cx="280" cy="178" rx="225" ry="75" fill="url(#vz-cloud-glow)" />
        <g class="vz-cloud-shadow" fill="#0ea5e9" opacity="0.16" filter="url(#vz-cloud-shadow)">
          <ellipse cx="278" cy="205" rx="182" ry="40" />
        </g>
        <g class="vz-cloud-body" filter="url(#vz-cloud-soft)">
          <ellipse cx="280" cy="196" rx="188" ry="54" fill="url(#vz-cloud-white)" />
          <circle cx="138" cy="169" r="62" fill="url(#vz-cloud-white)" />
          <circle cx="208" cy="125" r="80" fill="url(#vz-cloud-white)" />
          <circle cx="300" cy="108" r="92" fill="url(#vz-cloud-white)" />
          <circle cx="394" cy="132" r="72" fill="url(#vz-cloud-white)" />
          <circle cx="438" cy="176" r="54" fill="url(#vz-cloud-white)" />
        </g>
        <g class="vz-cloud-highlight" fill="#ffffff" opacity="0.5" filter="url(#vz-cloud-soft)">
          <ellipse cx="218" cy="119" rx="42" ry="22" />
          <ellipse cx="335" cy="100" rx="52" ry="25" />
          <ellipse cx="413" cy="143" rx="30" ry="14" />
        </g>
        <g class="vz-cloud-spark" fill="#bae6fd">
          <circle cx="132" cy="221" r="3" />
          <circle cx="172" cy="233" r="2" />
          <circle cx="405" cy="225" r="2.5" />
          <circle cx="447" cy="207" r="2" />
          <circle cx="342" cy="236" r="2" />
        </g>
      </svg>
    </div>
    <div class="vz-scene-label">
      <span>CLOUD RESOURCE FIELD</span>
      <b>虚拟化云资源态势</b>
    </div>
    <div class="vz-scene-stats">
      <div v-for="item in stats" :key="item.key" class="vz-scene-stat" :class="item.tone">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>
    <div class="vz-scene-orbit">LIVE · {{ platformCount }} PLATFORM / {{ hostCount }} HOST / {{ vmCount }} VM</div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as THREE from 'three'

const props = defineProps({
  platforms: { type: Array, default: () => [] },
  hosts: { type: Array, default: () => [] },
  vms: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
})

const hostRef = ref(null)
const canvasRef = ref(null)
const platformCount = computed(() => props.platforms.length)
const hostCount = computed(() => props.hosts.length)
const vmCount = computed(() => props.vms.length)
const stats = computed(() => [
  { key: 'cpu', label: 'CPU', value: `${Number(props.summary.cpu || 0).toFixed(1)}%`, tone: 'cyan' },
  { key: 'memory', label: 'MEM', value: `${Number(props.summary.memory || 0).toFixed(1)}%`, tone: 'violet' },
  { key: 'disk', label: 'DISK', value: `${Number(props.summary.disk || 0).toFixed(1)}%`, tone: 'amber' },
])

let renderer = null
let scene = null
let camera = null
let frame = 0
let resizeObserver = null
let group = null
let ringA = null
let ringB = null
let nodeGroup = null
let particles = null

function makeNode(color, size) {
  const geometry = new THREE.SphereGeometry(size, 10, 10)
  const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9 })
  const mesh = new THREE.Mesh(geometry, material)
  mesh.userData.phase = Math.random() * Math.PI * 2
  return mesh
}

function addArc(a, b, color) {
  const start = a.clone()
  const end = b.clone()
  const mid = start.clone().add(end).multiplyScalar(0.5)
  const distance = start.distanceTo(end)
  mid.normalize().multiplyScalar(2.7 + distance * 0.15)
  const curve = new THREE.QuadraticBezierCurve3(start, mid, end)
  const points = curve.getPoints(36)
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const material = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.18 })
  return new THREE.Line(geometry, material)
}

function buildScene() {
  if (!canvasRef.value || !hostRef.value) return
  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100)
  camera.position.set(0, 0.2, 8)
  renderer = new THREE.WebGLRenderer({ canvas: canvasRef.value, alpha: true, antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setClearColor(0x000000, 0)
  group = new THREE.Group()
  scene.add(group)

  // 白云主体使用 SVG 云朵叠加层，Three.js 只保留轨道、节点和粒子。
  ringA = new THREE.Mesh(
    new THREE.TorusGeometry(2.75, 0.015, 6, 96),
    new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.5 }),
  )
  ringA.rotation.x = Math.PI / 2.7
  ringA.rotation.y = 0.3
  group.add(ringA)

  ringB = new THREE.Mesh(
    new THREE.TorusGeometry(2.98, 0.01, 6, 96),
    new THREE.MeshBasicMaterial({ color: 0xa78bfa, transparent: true, opacity: 0.3 }),
  )
  ringB.rotation.x = Math.PI / 1.9
  ringB.rotation.z = 0.45
  group.add(ringB)

  nodeGroup = new THREE.Group()
  const palette = [0x38bdf8, 0xa78bfa, 0xfbbf24, 0x34d399]
  const count = Math.min(14, Math.max(6, hostCount.value + platformCount.value * 2))
  const positions = []
  for (let i = 0; i < count; i += 1) {
    const angle = (i / count) * Math.PI * 2
    const node = makeNode(palette[i % palette.length], i % 4 === 0 ? 0.075 : 0.045)
    node.position.set(
      Math.cos(angle) * (1.9 + (i % 3) * 0.22),
      0.22 + Math.sin(angle * 1.5) * 0.85,
      0.35 + Math.sin(angle) * 0.75,
    )
    nodeGroup.add(node)
    positions.push(node.position.clone())
  }
  group.add(nodeGroup)

  for (let i = 0; i < positions.length; i += 1) {
    const target = positions[(i + 3) % positions.length]
    group.add(addArc(positions[i], target, palette[i % palette.length]))
  }

  const pointGeometry = new THREE.BufferGeometry()
  const pointPositions = new Float32Array(260 * 3)
  for (let i = 0; i < 260; i += 1) {
    const radius = 2.4 + Math.random() * 1.9
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    pointPositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
    pointPositions[i * 3 + 1] = radius * Math.cos(phi)
    pointPositions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta)
  }
  pointGeometry.setAttribute('position', new THREE.BufferAttribute(pointPositions, 3))
  particles = new THREE.Points(pointGeometry, new THREE.PointsMaterial({
    color: 0x7dd3fc,
    size: 0.022,
    transparent: true,
    opacity: 0.55,
    sizeAttenuation: true,
  }))
  group.add(particles)
}

function resize() {
  if (!hostRef.value || !renderer || !camera) return
  const width = Math.max(80, hostRef.value.clientWidth)
  const height = Math.max(80, hostRef.value.clientHeight)
  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function animate() {
  frame = requestAnimationFrame(animate)
  if (!group) return
  group.rotation.y += 0.0024
  group.rotation.x = Math.sin(Date.now() * 0.00018) * 0.08
  if (ringA) ringA.rotation.z += 0.003
  if (ringB) ringB.rotation.z -= 0.002
  if (particles) particles.rotation.y -= 0.0008
  if (nodeGroup) {
    nodeGroup.children.forEach((node) => {
      const scale = 1 + Math.sin(Date.now() * 0.002 + node.userData.phase) * 0.28
      node.scale.setScalar(scale)
    })
  }
  if (renderer && scene && camera) renderer.render(scene, camera)
}

onMounted(() => {
  buildScene()
  resize()
  animate()
  window.addEventListener('resize', resize)
  if (window.ResizeObserver && hostRef.value) {
    resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(hostRef.value)
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  window.removeEventListener('resize', resize)
  resizeObserver?.disconnect()
  renderer?.dispose()
  scene?.traverse((object) => {
    if (object.geometry) object.geometry.dispose()
    if (object.material) {
      if (Array.isArray(object.material)) object.material.forEach((item) => item.dispose())
      else object.material.dispose()
    }
  })
})
</script>

<style scoped>
.vz-scene {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 120px;
  overflow: hidden;
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: 10px;
  background:
    radial-gradient(circle at 50% 48%, rgba(14, 165, 233, 0.15), transparent 38%),
    radial-gradient(circle at 50% 50%, rgba(88, 28, 135, 0.18), transparent 64%),
    linear-gradient(160deg, rgba(2, 17, 33, 0.94), rgba(4, 11, 24, 0.72));
  box-shadow: inset 0 0 55px rgba(14, 165, 233, 0.08);
}

.vz-scene::before,
.vz-scene::after {
  position: absolute;
  width: 22px;
  height: 22px;
  border-color: rgba(56, 189, 248, 0.5);
  content: '';
  pointer-events: none;
}

.vz-scene::before { top: 8px; left: 8px; border-top: 1px solid; border-left: 1px solid; }
.vz-scene::after { right: 8px; bottom: 8px; border-right: 1px solid; border-bottom: 1px solid; }

.vz-scene-canvas { position: absolute; inset: 0; width: 100%; height: 100%; }

.vz-scene-grid {
  position: absolute;
  inset: 0;
  opacity: 0.16;
  background-image:
    linear-gradient(rgba(56, 189, 248, 0.22) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.22) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: radial-gradient(ellipse at center, #000 8%, transparent 72%);
  pointer-events: none;
}

.vz-cloud-art {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-items: center;
  pointer-events: none;
}

.vz-cloud-art svg {
  width: 64%;
  height: 72%;
  overflow: visible;
  filter: drop-shadow(0 0 22px rgba(147, 224, 255, 0.3));
  animation: vz-cloud-float 6.5s ease-in-out infinite;
}

.vz-cloud-body {
  transform-origin: 50% 62%;
  animation: vz-cloud-breathe 4.2s ease-in-out infinite;
}

.vz-cloud-highlight {
  animation: vz-cloud-shine 5s ease-in-out infinite;
}

.vz-cloud-shadow {
  animation: vz-cloud-shadow 4.2s ease-in-out infinite;
}

.vz-cloud-spark circle {
  animation: vz-cloud-spark 2.8s ease-in-out infinite;
}

.vz-cloud-spark circle:nth-child(2n) {
  animation-delay: 0.8s;
}

.vz-cloud-spark circle:nth-child(3n) {
  animation-delay: 1.5s;
}

@keyframes vz-cloud-float {
  0%, 100% { transform: translate3d(0, 5px, 0) rotate(-1deg) scale(0.985); }
  50% { transform: translate3d(0, -9px, 0) rotate(1deg) scale(1.015); }
}

@keyframes vz-cloud-breathe {
  0%, 100% { transform: scale(0.985); }
  50% { transform: scale(1.018); }
}

@keyframes vz-cloud-shine {
  0%, 100% { opacity: 0.32; transform: translateX(-5px); }
  50% { opacity: 0.65; transform: translateX(5px); }
}

@keyframes vz-cloud-shadow {
  0%, 100% { opacity: 0.11; transform: scaleX(0.95); }
  50% { opacity: 0.2; transform: scaleX(1.06); }
}

@keyframes vz-cloud-spark {
  0%, 100% { opacity: 0.2; }
  50% { opacity: 0.9; }
}

.vz-scene-label { position: absolute; top: 14px; left: 16px; display: flex; flex-direction: column; gap: 3px; }
.vz-scene-label span { color: #38bdf8; font-family: Consolas, monospace; font-size: 8px; letter-spacing: 1.8px; }
.vz-scene-label b { color: #e0f2fe; font-size: 12px; }

.vz-scene-stats { position: absolute; right: 14px; bottom: 32px; display: flex; flex-direction: column; gap: 5px; }
.vz-scene-stat { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-width: 112px; padding: 4px 7px; border: 1px solid rgba(56, 189, 248, 0.18); border-radius: 5px; background: rgba(3, 16, 30, 0.72); }
.vz-scene-stat span { color: #64748b; font-family: Consolas, monospace; font-size: 8px; }
.vz-scene-stat strong { color: #7dd3fc; font-family: Consolas, monospace; font-size: 10px; }
.vz-scene-stat.violet strong { color: #c4b5fd; }
.vz-scene-stat.amber strong { color: #fbbf24; }

.vz-scene-orbit { position: absolute; right: 16px; top: 16px; color: #64748b; font-family: Consolas, monospace; font-size: 8px; letter-spacing: 0.8px; }
</style>
