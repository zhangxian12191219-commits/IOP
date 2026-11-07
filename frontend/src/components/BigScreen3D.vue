<template>
  <div ref="hostRef" class="big3d-stage">
    <div class="big3d-vignette"></div>
    <div class="big3d-label">{{ mode === 'asset' ? 'ASSET DIGITAL TWIN' : 'VIRTUALIZATION ORBIT' }}</div>
    <div class="big3d-zoom-controls">
      <button type="button" title="放大" @click="manualZoom(-1)">＋</button>
      <button type="button" title="缩小" @click="manualZoom(1)">－</button>
      <button type="button" title="复位并自动放大" @click="resetZoom">复位</button>
      <button type="button" :class="{ active: autoZoom }" @click="toggleAutoZoom">{{ autoZoom ? '自动' : '手动' }}</button>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'

const props = defineProps({
  mode: { type: String, default: 'asset' },
  items: { type: Array, default: () => [] },
  alerts: { type: Array, default: () => [] },
  accent: { type: String, default: '#38bdf8' },
})

const hostRef = ref(null)
let renderer = null
let scene = null
let camera = null
let group = null
let stars = null
let animation = 0
let observer = null
let resizeTimer = null
let disposed = false
const autoZoom = ref(true)
let manualZoomFactor = 1
let displayZoom = 1
let assetLabels = []
let wheelHandler = null
let dblClickHandler = null
const focusPoint = new THREE.Vector3(0, 1.8, 0)

function makeMaterial(color, opacity = 0.8) {
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(color),
    emissive: new THREE.Color(color),
    emissiveIntensity: 0.55,
    transparent: true,
    opacity,
    roughness: 0.3,
    metalness: 0.45,
  })
}

function disposeGroup(target) {
  if (!target) return
  target.traverse((child) => {
    child.geometry?.dispose?.()
    const materials = Array.isArray(child.material) ? child.material : [child.material]
    materials.filter(Boolean).forEach((item) => {
      item.map?.dispose?.()
      item.dispose?.()
    })
  })
}

function clearSceneGroup() {
  if (!group) return
  scene.remove(group)
  disposeGroup(group)
  group = null
}

function addStars() {
  const geometry = new THREE.BufferGeometry()
  const count = 520
  const positions = new Float32Array(count * 3)
  for (let i = 0; i < count; i += 1) {
    const radius = 22 + Math.random() * 38
    const angle = Math.random() * Math.PI * 2
    const y = (Math.random() - 0.45) * 28
    positions[i * 3] = Math.cos(angle) * radius
    positions[i * 3 + 1] = y
    positions[i * 3 + 2] = Math.sin(angle) * radius
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const material = new THREE.PointsMaterial({
    color: new THREE.Color('#67e8f9'),
    size: 0.09,
    transparent: true,
    opacity: 0.6,
    depthWrite: false,
  })
  stars = new THREE.Points(geometry, material)
  scene.add(stars)
}

const ALERT_RANK = { info: 1, warning: 2, critical: 3, emergency: 4 }

function itemAlertLevel(item) {
  const id = item?.deviceId
  const name = String(item?.name || '')
  let best = ''
  let rank = 0
  for (const alert of props.alerts) {
    const matches = (id != null && Number(alert.device_id) === Number(id))
      || (name && String(alert.device_name || '') === name)
    if (!matches) continue
    const value = ALERT_RANK[alert.alert_level] || 0
    if (value > rank) { rank = value; best = alert.alert_level }
  }
  return best
}

function alertColor(level) {
  if (level === 'emergency') return '#fb7185'
  if (level === 'critical') return '#f97316'
  return '#fbbf24'
}

function makeAssetLabel(text, color = '#34d399') {
  const label = String(text || '未命名资产').trim().slice(0, 16) || '未命名资产'
  const canvas = document.createElement('canvas')
  canvas.width = 320
  canvas.height = 80
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = 'rgba(4, 15, 27, 0.82)'
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  const x = 6
  const y = 8
  const w = canvas.width - 12
  const h = canvas.height - 16
  const r = 12
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = '#e8fbff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  let fontSize = 32
  do {
    ctx.font = `700 ${fontSize}px "Microsoft YaHei", "PingFang SC", sans-serif`
    fontSize -= 1
  } while (ctx.measureText(label).width > w - 14 && fontSize > 18)
  ctx.fillText(label, canvas.width / 2, canvas.height / 2 + 1)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter
  texture.magFilter = THREE.LinearFilter
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity: 0.96,
    depthWrite: false,
  }))
  const width = Math.max(1.8, Math.min(3.2, 1.0 + label.length * 0.14))
  sprite.scale.set(width, 0.66, 1)
  sprite.center.set(0.5, 0)
  sprite.renderOrder = 4
  sprite.userData.isAssetLabel = true
  sprite.userData.labelBaseWidth = width
  sprite.userData.labelBaseHeight = 0.66
  return sprite
}

function buildAssetScene() {
  const grid = new THREE.GridHelper(42, 28, 0x1a6b8c, 0x0b3146)
  grid.material.transparent = true
  grid.material.opacity = 0.28
  grid.position.y = 0
  group.add(grid)

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(11.5, 11.65, 96),
    new THREE.MeshBasicMaterial({ color: new THREE.Color('#22d3ee'), transparent: true, opacity: 0.28, side: THREE.DoubleSide }),
  )
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.02
  group.add(ring)

  const items = props.items.slice(0, 56)
  const cols = Math.max(4, Math.ceil(Math.sqrt(Math.max(1, items.length))))
  const spacing = 2.15
  items.forEach((item, index) => {
    const row = Math.floor(index / cols)
    const col = index % cols
    const x = (col - (cols - 1) / 2) * spacing
    const z = (row - (Math.ceil(items.length / cols) - 1) / 2) * spacing
    const value = Math.max(8, Math.min(100, Number(item.value) || 20))
    const height = 0.55 + (value / 100) * 5.5
    const color = item.color || (item.online ? '#34d399' : '#fb7185')
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(0.72, height, 0.72),
      makeMaterial(color, item.online === false ? 0.46 : 0.78),
    )
    bar.position.set(x, height / 2 + 0.05, z)
    bar.userData.phase = Math.random() * Math.PI * 2
    bar.userData.baseY = bar.position.y
    group.add(bar)

    const cap = new THREE.Mesh(
      new THREE.SphereGeometry(0.11, 10, 10),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.9 }),
    )
    cap.position.set(x, height + 0.18, z)
    group.add(cap)

    const alertLevel = itemAlertLevel(item)
    const labelColor = alertLevel ? alertColor(alertLevel) : color
    const label = makeAssetLabel(item.name || item.label || '未命名资产', labelColor)
    if (label) {
      label.position.set(x, height + 0.34, z)
      group.add(label)
      assetLabels.push(label)
    }
    if (alertLevel) {
      const aColor = alertColor(alertLevel)
      const alertRing = new THREE.Mesh(
        new THREE.TorusGeometry(0.66, 0.045, 8, 36),
        new THREE.MeshBasicMaterial({
          color: new THREE.Color(aColor),
          transparent: true,
          opacity: 0.9,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      )
      alertRing.rotation.x = Math.PI / 2
      alertRing.position.set(x, 0.08, z)
      alertRing.userData.alertPulse = true
      alertRing.userData.alertBaseScale = 1
      alertRing.userData.alertPhase = Math.random() * Math.PI * 2
      group.add(alertRing)

      const beamHeight = height + 2.2
      const alertBeam = new THREE.Mesh(
        new THREE.CylinderGeometry(0.045, 0.16, beamHeight, 8, 1, true),
        new THREE.MeshBasicMaterial({
          color: new THREE.Color(aColor),
          transparent: true,
          opacity: 0.26,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          side: THREE.DoubleSide,
        }),
      )
      alertBeam.position.set(x, beamHeight / 2, z)
      alertBeam.userData.alertPulse = true
      alertBeam.userData.alertPhase = Math.random() * Math.PI * 2
      alertBeam.userData.alertBeam = true
      group.add(alertBeam)
    }
  })

  group.rotation.x = 0.06
}

function buildVirtualScene() {
  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(2.1, 1),
    new THREE.MeshStandardMaterial({
      color: new THREE.Color('#22d3ee'),
      emissive: new THREE.Color('#0e7490'),
      emissiveIntensity: 0.9,
      wireframe: true,
      transparent: true,
      opacity: 0.72,
    }),
  )
  core.position.y = 3.1
  group.add(core)

  const shell = new THREE.Mesh(
    new THREE.SphereGeometry(2.9, 22, 16),
    new THREE.MeshBasicMaterial({ color: new THREE.Color('#38bdf8'), wireframe: true, transparent: true, opacity: 0.12 }),
  )
  shell.position.y = 3.1
  group.add(shell)

  const platformAlerts = (props.alerts || []).filter((alert) => (
    !alert?.vm_id || String(alert?.alert_type || '').startsWith('platform_')
  ))
  if (platformAlerts.length) {
    const highest = platformAlerts.reduce((level, alert) => (
      (ALERT_RANK[alert.alert_level] || 0) > (ALERT_RANK[level] || 0) ? alert.alert_level : level
    ), platformAlerts[0]?.alert_level || 'warning')
    const aColor = alertColor(highest)
    core.material.color.set(aColor)
    core.material.emissive.set(aColor)
    shell.material.color.set(aColor)
    shell.material.opacity = 0.2

    const coreAlertRing = new THREE.Mesh(
      new THREE.TorusGeometry(3.15, 0.055, 8, 96),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(aColor),
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    )
    coreAlertRing.rotation.x = Math.PI / 2
    coreAlertRing.position.y = 3.1
    coreAlertRing.userData.alertPulse = true
    coreAlertRing.userData.alertPhase = Math.random() * Math.PI * 2
    group.add(coreAlertRing)

    const countLabel = makeAssetLabel(`平台告警 ${platformAlerts.length} 条`, aColor)
    if (countLabel) {
      countLabel.position.set(0, 6.35, 0)
      group.add(countLabel)
      assetLabels.push(countLabel)
    }
    platformAlerts.slice(0, 3).forEach((alert, index) => {
      const title = alert.platform_name || alert.vm_name || '虚拟化平台'
      const detail = alert.alert_type_text || alert.metric_name || alert.message || '告警'
      const label = makeAssetLabel(`${title}：${detail}`, aColor)
      if (!label) return
      const angle = (index / 3) * Math.PI * 2 + Math.PI / 6
      label.position.set(Math.cos(angle) * 4.1, 4.65 + index * 0.22, Math.sin(angle) * 4.1)
      group.add(label)
      assetLabels.push(label)
    })
  }

  const items = props.items.slice(0, 18)
  const count = Math.max(1, items.length)
  const radius = 6.2
  const hostMeshes = []
  items.forEach((item, index) => {
    const angle = (index / count) * Math.PI * 2
    const x = Math.cos(angle) * radius
    const z = Math.sin(angle) * radius
    const y = 3.1 + Math.sin(angle * 1.7) * 1.5
    const color = item.color || (item.online === false ? '#fb7185' : '#a78bfa')
    const host = new THREE.Mesh(
      new THREE.SphereGeometry(0.42 + Math.min(0.5, (Number(item.value) || 20) / 180), 18, 14),
      makeMaterial(color, 0.88),
    )
    host.position.set(x, y, z)
    host.userData.phase = Math.random() * Math.PI * 2
    host.userData.baseY = y
    group.add(host)
    hostMeshes.push(host)

    const hostLabel = makeAssetLabel(item.name || item.label || '未命名宿主机', color)
    if (hostLabel) {
      hostLabel.position.set(x, y + 0.72, z)
      group.add(hostLabel)
      assetLabels.push(hostLabel)
    }

    const points = [new THREE.Vector3(0, 3.1, 0), new THREE.Vector3(x, y, z)]
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.22 }),
    )
    group.add(line)

    const vmCount = Math.min(7, Math.max(1, Number(item.vms) || 2))
    for (let j = 0; j < vmCount; j += 1) {
      const a = (j / vmCount) * Math.PI * 2 + index
      const vm = new THREE.Mesh(
        new THREE.SphereGeometry(0.09, 8, 8),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(item.vmColor || '#67e8f9'), transparent: true, opacity: 0.8 }),
      )
      vm.position.set(x + Math.cos(a) * 0.9, y + (Math.random() - 0.5) * 0.75, z + Math.sin(a) * 0.9)
      group.add(vm)
    }
  })

  const ringColors = ['#38bdf8', '#a78bfa', '#34d399']
  ringColors.forEach((color, i) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(4.2 + i * 1.15, 0.015, 8, 140),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.28 }),
    )
    ring.position.y = 3.1
    ring.rotation.x = Math.PI / 2 + i * 0.35
    ring.rotation.y = i * 0.4
    group.add(ring)
  })

  const grid = new THREE.GridHelper(38, 24, 0x1a6b8c, 0x0b3146)
  grid.material.transparent = true
  grid.material.opacity = 0.2
  grid.position.y = 0
  group.add(grid)
}

function contentBounds(target) {
  const box = new THREE.Box3()
  target.updateMatrixWorld(true)
  target.traverse((child) => {
    if (!child.isMesh && !child.isLine && !child.isPoints) return
    if (child.type === 'GridHelper') return
    if (!child.geometry) return
    child.geometry.computeBoundingBox()
    if (!child.geometry.boundingBox) return
    box.union(child.geometry.boundingBox.clone().applyMatrix4(child.matrixWorld))
  })
  return box
}

function rebuild() {
  if (!scene) return
  clearSceneGroup()
  assetLabels = []
  group = new THREE.Group()
  scene.add(group)
  if (props.mode === 'virtual') buildVirtualScene()
  else buildAssetScene()
  group.rotation.y = 0
  // 按实际 3D 内容包围盒把图形移到画布中心，不再假设内容天然以原点对称
  const box = contentBounds(group)
  if (!box.isEmpty()) {
    const center = box.getCenter(new THREE.Vector3())
    group.position.x -= center.x
    group.position.z -= center.z
    const shifted = contentBounds(group)
    const shiftedCenter = shifted.isEmpty() ? center : shifted.getCenter(new THREE.Vector3())
    focusPoint.set(0, shiftedCenter.y, 0)
  } else {
    focusPoint.set(0, props.mode === 'virtual' ? 3.1 : 1.8, 0)
  }
}

function resize() {
  if (!renderer || !hostRef.value) return
  const width = hostRef.value.clientWidth || 900
  const height = hostRef.value.clientHeight || 560
  renderer.setSize(width, height, false)
  camera.aspect = width / Math.max(1, height)
  camera.updateProjectionMatrix()
}

function animate() {
  if (disposed) return
  animation = requestAnimationFrame(animate)
  const t = performance.now() * 0.001
  if (group) {
    group.rotation.y += props.mode === 'virtual' ? 0.0022 : 0.0012
    group.children.forEach((child) => {
      if (child.userData.phase !== undefined) {
        child.position.y = child.userData.baseY + Math.sin(t * 1.7 + child.userData.phase) * 0.08
      }
      if (child.userData.alertPulse) {
        const pulse = 0.5 + 0.5 * Math.sin(t * 3.2 + (child.userData.alertPhase || 0))
        if (child.userData.alertBeam) {
          child.material.opacity = 0.12 + pulse * 0.32
          child.scale.x = 0.8 + pulse * 0.55
          child.scale.z = 0.8 + pulse * 0.55
        } else {
          const scale = 1 + pulse * 0.34
          child.scale.setScalar(scale)
          child.material.opacity = 0.45 + pulse * 0.5
        }
      }
    })
  }
  if (stars) stars.rotation.y = t * 0.008
  if (camera) {
    let targetZoom = manualZoomFactor
    if (autoZoom.value) {
      // 12 秒一轮缓慢推近/拉远，让资产/宿主机名称周期性地清晰可读。
      const breathing = (Math.sin(t * 0.52) + 1) / 2
      targetZoom = 0.52 + breathing * 0.48
    }
    displayZoom += (targetZoom - displayZoom) * 0.045
    const baseY = props.mode === 'virtual' ? 14 : 17
    const baseZ = props.mode === 'virtual' ? 24 : 32
    const activeZoom = displayZoom
    camera.position.x = Math.sin(t * 0.13) * 1.4 * activeZoom
    camera.position.y = focusPoint.y + (baseY - focusPoint.y) * activeZoom + Math.sin(t * 0.2) * 0.4
    camera.position.z = baseZ * activeZoom
    camera.lookAt(focusPoint)
    // 标签随镜头远近平滑保持可读大小
    for (const label of assetLabels) {
      const distance = camera.position.distanceTo(label.getWorldPosition(label.position.clone()))
      const scale = Math.max(0.72, Math.min(1.55, distance / 26))
      label.scale.set(
        (label.userData.labelBaseWidth || 2.5) * scale,
        (label.userData.labelBaseHeight || 0.66) * scale,
        1,
      )
    }
  }
  renderer.render(scene, camera)
}

function manualZoom(direction) {
  if (autoZoom.value) {
    manualZoomFactor = displayZoom
    autoZoom.value = false
  }
  manualZoomFactor = Math.max(0.28, Math.min(1.35, manualZoomFactor + direction * 0.16))
}

function resetZoom() {
  manualZoomFactor = 1
  displayZoom = 1
  autoZoom.value = true
}

function toggleAutoZoom() {
  autoZoom.value = !autoZoom.value
  if (autoZoom.value) manualZoomFactor = 1
}

onMounted(() => {
  if (!hostRef.value) return
  try {
    scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x03101c, 0.021)
    camera = new THREE.PerspectiveCamera(44, 1, 0.1, 300)
    camera.position.set(0, props.mode === 'virtual' ? 14 : 17, props.mode === 'virtual' ? 24 : 32)
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setClearColor(0x000000, 0)
    hostRef.value.appendChild(renderer.domElement)
    wheelHandler = (event) => {
      event.preventDefault()
      autoZoom.value = false
      manualZoomFactor = Math.max(0.28, Math.min(1.35, manualZoomFactor * (event.deltaY > 0 ? 1.08 : 0.92)))
    }
    dblClickHandler = () => resetZoom()
    renderer.domElement.addEventListener('wheel', wheelHandler, { passive: false })
    renderer.domElement.addEventListener('dblclick', dblClickHandler)
    scene.add(new THREE.AmbientLight(0x67e8f9, 0.8))
    const light = new THREE.DirectionalLight(0x38bdf8, 2.2)
    light.position.set(8, 18, 12)
    scene.add(light)
    const fill = new THREE.PointLight(0xa78bfa, 1.1, 55)
    fill.position.set(-12, 8, -8)
    scene.add(fill)
    addStars()
    rebuild()
    resize()
    animate()
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => {
        window.clearTimeout(resizeTimer)
        resizeTimer = window.setTimeout(resize, 60)
      })
      observer.observe(hostRef.value)
    } else {
      window.addEventListener('resize', resize)
    }
  } catch (error) {
    console.warn('3D big screen unavailable', error)
  }
})

watch(() => props.items, rebuild, { deep: true })
watch(() => props.alerts, rebuild, { deep: true })
watch(() => props.mode, () => {
  manualZoomFactor = 1
  displayZoom = 1
  autoZoom.value = true
  if (camera) camera.position.z = props.mode === 'virtual' ? 24 : 32
  rebuild()
})

onBeforeUnmount(() => {
  disposed = true
  cancelAnimationFrame(animation)
  observer?.disconnect()
  clearTimeout(resizeTimer)
  if (renderer?.domElement) {
    if (wheelHandler) renderer.domElement.removeEventListener('wheel', wheelHandler)
    if (dblClickHandler) renderer.domElement.removeEventListener('dblclick', dblClickHandler)
  }
  window.removeEventListener('resize', resize)
  clearSceneGroup()
  disposeGroup(stars)
  stars = null
  renderer?.dispose()
  renderer = null
  scene = null
  camera = null
})
</script>

<style scoped>
.big3d-stage { position: relative; width: 100%; height: 100%; min-height: 260px; overflow: hidden; background: radial-gradient(circle at 50% 50%, rgba(14, 116, 144, 0.12), transparent 62%); }
.big3d-stage canvas { display: block; width: 100%; height: 100%; }
.big3d-vignette { position: absolute; inset: 0; pointer-events: none; background: radial-gradient(circle at 50% 50%, transparent 30%, rgba(2, 8, 15, 0.62) 100%); }
.big3d-label { position: absolute; left: 16px; top: 12px; color: rgba(103, 232, 249, 0.58); font-size: 9px; letter-spacing: 2px; pointer-events: none; }
.big3d-zoom-controls { position: absolute; right: 10px; bottom: 10px; z-index: 3; display: flex; gap: 5px; padding: 4px; border: 1px solid rgba(56, 189, 248, 0.22); border-radius: 8px; background: rgba(3, 16, 28, 0.72); backdrop-filter: blur(5px); }
.big3d-zoom-controls button { min-width: 28px; height: 24px; padding: 0 7px; border: 1px solid rgba(56, 189, 248, 0.22); border-radius: 5px; background: rgba(8, 30, 48, 0.8); color: #bae6fd; font-size: 11px; cursor: pointer; }
.big3d-zoom-controls button:hover { border-color: #38bdf8; color: #fff; }
.big3d-zoom-controls button.active { border-color: #34d399; background: rgba(6, 78, 59, 0.7); color: #a7f3d0; }
</style>
