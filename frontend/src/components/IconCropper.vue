<template>
  <el-dialog
    :model-value="modelValue"
    title="裁剪 / 缩放图标"
    width="460px"
    top="8vh"
    @update:model-value="(v) => emit('update:modelValue', v)"
    @opened="init"
    @closed="cleanup"
  >
    <div class="cropper-wrap">
      <canvas
        ref="canvasRef"
        width="320"
        height="320"
        class="cropper-canvas"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @wheel.prevent="onWheel"
      />
      <div class="cropper-mask">
        <div class="crop-frame" />
      </div>
    </div>

    <div class="cropper-controls">
      <span class="ctrl-label">缩放</span>
      <el-slider v-model="zoom" :min="1" :max="4" :step="0.05" style="flex: 1" @input="draw" />
      <el-button size="small" @click="reset">重置</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="拖动图片调整位置，滑块或滚轮缩放；输出 256×256 PNG，适配资产列表与拓扑图标"
    />

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="processing" :disabled="!ready" @click="confirm">
        应用裁剪
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  src: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'done'])

const canvasRef = ref(null)
const zoom = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const processing = ref(false)
const ready = ref(false)

const SIZE = 320
const OUTPUT = 256
let img = null
let baseScale = 1
let dragging = false
let startX = 0
let startY = 0
let startOffsetX = 0
let startOffsetY = 0

function init() {
  if (!props.src) return
  ready.value = false
  img = new Image()
  img.onload = () => {
    baseScale = Math.max(SIZE / img.naturalWidth, SIZE / img.naturalHeight)
    reset()
    ready.value = true
    nextTick(draw)
  }
  img.onerror = () => {
    ElMessage.error('图片加载失败，无法裁剪')
    emit('update:modelValue', false)
  }
  img.src = props.src
}

function cleanup() {
  img = null
  ready.value = false
  zoom.value = 1
  offsetX.value = 0
  offsetY.value = 0
}

function reset() {
  zoom.value = 1
  offsetX.value = 0
  offsetY.value = 0
  draw()
}

function scaledSize() {
  if (!img) return { w: 0, h: 0 }
  const scale = baseScale * zoom.value
  return { w: img.naturalWidth * scale, h: img.naturalHeight * scale }
}

function clampOffsets() {
  const { w, h } = scaledSize()
  const maxX = Math.max(0, (w - SIZE) / 2)
  const maxY = Math.max(0, (h - SIZE) / 2)
  offsetX.value = Math.min(maxX, Math.max(-maxX, offsetX.value))
  offsetY.value = Math.min(maxY, Math.max(-maxY, offsetY.value))
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas || !img) return
  const ctx = canvas.getContext('2d')
  clampOffsets()
  const { w, h } = scaledSize()
  const x = SIZE / 2 - w / 2 + offsetX.value
  const y = SIZE / 2 - h / 2 + offsetY.value

  ctx.clearRect(0, 0, SIZE, SIZE)
  ctx.fillStyle = '#f5f7fa'
  ctx.fillRect(0, 0, SIZE, SIZE)
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(img, x, y, w, h)
}

function onPointerDown(event) {
  if (!ready.value) return
  dragging = true
  startX = event.clientX
  startY = event.clientY
  startOffsetX = offsetX.value
  startOffsetY = offsetY.value
  event.target.setPointerCapture?.(event.pointerId)
}

function onPointerMove(event) {
  if (!dragging) return
  offsetX.value = startOffsetX + (event.clientX - startX)
  offsetY.value = startOffsetY + (event.clientY - startY)
  draw()
}

function onPointerUp() {
  dragging = false
}

function onWheel(event) {
  if (!ready.value) return
  zoom.value = Math.min(4, Math.max(1, zoom.value - Math.sign(event.deltaY) * 0.08))
  draw()
}

function confirm() {
  if (!img || !ready.value) return
  processing.value = true
  try {
    const out = document.createElement('canvas')
    out.width = OUTPUT
    out.height = OUTPUT
    const ctx = out.getContext('2d')
    const factor = OUTPUT / SIZE
    const { w, h } = scaledSize()
    const x = (SIZE / 2 - w / 2 + offsetX.value) * factor
    const y = (SIZE / 2 - h / 2 + offsetY.value) * factor
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, OUTPUT, OUTPUT)
    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(img, x, y, w * factor, h * factor)

    out.toBlob(
      (blob) => {
        processing.value = false
        if (!blob) {
          ElMessage.error('生成裁剪图片失败')
          return
        }
        const file = new File([blob], `icon-${Date.now()}.png`, { type: 'image/png' })
        emit('done', file)
        emit('update:modelValue', false)
      },
      'image/png',
      0.95
    )
  } catch (e) {
    processing.value = false
    ElMessage.error(e.message || '裁剪失败（跨域图片不支持裁剪）')
  }
}
</script>

<style scoped>
.cropper-wrap {
  position: relative;
  width: 320px;
  height: 320px;
  margin: 0 auto 14px;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  overflow: hidden;
  cursor: grab;
  user-select: none;
}

.cropper-wrap:active {
  cursor: grabbing;
}

.cropper-canvas {
  display: block;
  width: 320px;
  height: 320px;
}

.cropper-mask {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.35)) top / 100% 38px no-repeat,
    linear-gradient(rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.35)) bottom / 100% 38px no-repeat,
    linear-gradient(rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.35)) left / 38px 100% no-repeat,
    linear-gradient(rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.35)) right / 38px 100% no-repeat;
}

.crop-frame {
  position: absolute;
  inset: 38px;
  border: 2px dashed rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.25);
}

.cropper-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.ctrl-label {
  font-size: 13px;
  color: #606266;
  width: 40px;
}
</style>
