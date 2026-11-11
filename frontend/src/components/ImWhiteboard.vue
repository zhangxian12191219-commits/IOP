<template>
  <div v-if="imState.whiteboard.open" class="im-wb-layer">
    <div class="im-wb-panel">
      <header class="im-wb-head">
        <div class="im-wb-title">
          <el-icon><EditPen /></el-icon>
          <strong>{{ whiteboardTitle }}</strong>
          <span class="im-wb-group">{{ groupName }}</span>
          <el-tag size="small" effect="plain" round>
            {{ imState.whiteboard.loading ? '加载中…' : `${imState.whiteboard.strokes.length} 笔` }}
          </el-tag>
        </div>
        <div class="im-wb-tools">
          <el-color-picker
            v-model="color"
            size="small"
            :predefine="predefineColors"
            popper-class="im-wb-color-popper"
            title="画笔颜色"
          />
          <el-select
            v-model="width"
            size="small"
            class="im-wb-width"
            popper-class="im-wb-width-popper"
            title="笔触粗细"
          >
            <el-option v-for="item in widths" :key="item" :label="`${item}px`" :value="item" />
          </el-select>
          <div class="im-wb-tool-group">
            <button
              v-for="item in toolOptions"
              :key="item.value"
              type="button"
              class="im-wb-tool"
              :class="{ active: tool === item.value }"
              @click="tool = item.value"
            >
              <el-icon><component :is="item.icon" /></el-icon>{{ item.label }}
            </button>
          </div>
          <el-button size="small" @click="undoWhiteboard">
            <el-icon><RefreshLeft /></el-icon>撤销
          </el-button>
          <el-button size="small" @click="handleClear">
            <el-icon><Delete /></el-icon>清空
          </el-button>
        </div>
        <el-button size="small" class="im-wb-close" @click="closeWhiteboard">
          <el-icon><Close /></el-icon>关闭
        </el-button>
      </header>

      <div
        ref="stageRef"
        class="im-wb-stage"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @pointerleave="onPointerLeave"
        @contextmenu.prevent
      >
        <canvas ref="canvasRef" class="im-wb-canvas"></canvas>
        <span
          v-if="localLaser"
          class="im-wb-pointer is-local"
          :style="{ left: `${localLaser.x * 100}%`, top: `${localLaser.y * 100}%` }"
        >
          <i></i><em>我</em>
        </span>
        <span
          v-for="pointer in pointers"
          :key="pointer.id"
          class="im-wb-pointer"
          :style="{ left: `${pointer.x * 100}%`, top: `${pointer.y * 100}%` }"
        >
          <i></i><em>{{ pointer.name }}</em>
        </span>
        <div v-if="!imState.whiteboard.strokes.length && !drawing" class="im-wb-empty">
          <el-icon :size="30"><EditPen /></el-icon>
          <strong>一起画点什么</strong>
          <span>群成员或单聊双方会实时看到你的笔迹；笔画只保留 15 天。</span>
        </div>
        <div class="im-wb-hint">画笔 / 橡皮支持拖拽绘制 · 激光仅实时指示不保存</div>
        <div v-if="clearConfirm" class="im-wb-clear-confirm" @pointerdown.stop>
          <span>清空后当前白板的全部笔画都会被删除（单聊双方 / 群聊所有成员），且无法恢复。是否继续？</span>
          <div class="im-wb-clear-actions">
            <el-button size="small" @click="clearConfirm = false">取消</el-button>
            <el-button size="small" type="danger" @click="confirmClearWhiteboard">确定清空</el-button>
          </div>
        </div>
      </div>

      <footer class="im-wb-foot">
        <span>当前工具：{{ currentToolLabel }} · 颜色 {{ color }} · 粗细 {{ width }}px</span>
        <span>白板内容与聊天消息一样只保留 {{ imState.retentionDays || 15 }} 天</span>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Aim, Brush, EditPen } from '@element-plus/icons-vue'
import {
  closeWhiteboard, clearWhiteboard, imState, sendWhiteboardPointer,
  sendWhiteboardStroke, undoWhiteboard,
} from '@/store/im'

const stageRef = ref(null)
const canvasRef = ref(null)
const color = ref(localStorage.getItem('nms_im_wb_color') || '#67e8f9')
const width = ref(Number(localStorage.getItem('nms_im_wb_width') || 4))
const tool = ref('pen')
const widths = [2, 3, 4, 6, 9, 14, 20]
const predefineColors = ['#67e8f9', '#22d3ee', '#34d399', '#fbbf24', '#fb7185', '#a78bfa', '#f8fafc', '#0f172a']
const toolOptions = [
  { value: 'pen', label: '画笔', icon: EditPen },
  { value: 'eraser', label: '橡皮', icon: Brush },
  { value: 'laser', label: '激光', icon: Aim },
]

let drawing = false
let currentStroke = null
const localLaser = ref(null)
const clearConfirm = ref(false)
let resizeObserver = null
let dpr = 1

const whiteboardTitle = computed(() => imState.whiteboard.peerId ? '单聊白板' : '群白板')
const groupName = computed(() => {
  if (imState.whiteboard.peerId) {
    const peer = (imState.users || []).find((item) => Number(item.id) === Number(imState.whiteboard.peerId))
    return peer?.real_name || peer?.username || '单聊对象'
  }
  const group = imState.groups.find((item) => item.id === imState.whiteboard.groupId)
  return group?.name || '群组'
})
const pointers = computed(() => Object.entries(imState.whiteboardPointers || {})
  .map(([id, pointer]) => ({ id, ...pointer })))
const currentToolLabel = computed(
  () => toolOptions.find((item) => item.value === tool.value)?.label || '画笔',
)

watch(color, (value) => value && localStorage.setItem('nms_im_wb_color', value))
watch(width, (value) => value && localStorage.setItem('nms_im_wb_width', String(value)))
watch(() => imState.whiteboard.strokes, () => redraw(), { deep: false })
watch(() => imState.whiteboard.open, async (open) => {
  if (!open) {
    clearConfirm.value = false
    resizeObserver?.disconnect()
    resizeObserver = null
    return
  }
  await nextTick()
  attachCanvas()
})

onMounted(() => {
  if (imState.whiteboard.open) nextTick(attachCanvas)
})

function setupCanvasSize() {
  const canvas = canvasRef.value
  const stage = stageRef.value
  if (!canvas || !stage) return
  dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2))
  const rect = stage.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  canvas.width = Math.round(rect.width * dpr)
  canvas.height = Math.round(rect.height * dpr)
  canvas.style.width = '100%'
  canvas.style.height = '100%'
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function attachCanvas() {
  setupCanvasSize()
  if (!stageRef.value) return
  // 白板每次打开都会重建 DOM，这里重新绑定尺寸监听，避免监听旧的已卸载节点
  resizeObserver?.disconnect()
  resizeObserver = new ResizeObserver(() => {
    setupCanvasSize()
    redraw()
  })
  resizeObserver.observe(stageRef.value)
  redraw()
}

function drawStroke(ctx, stroke) {
  if (!stroke?.points?.length) return
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect) return
  ctx.save()
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.globalCompositeOperation = stroke.tool === 'eraser' ? 'destination-out' : 'source-over'
  ctx.strokeStyle = stroke.color || '#67e8f9'
  ctx.fillStyle = stroke.color || '#67e8f9'
  ctx.lineWidth = Number(stroke.width || 3)
  ctx.beginPath()
  stroke.points.forEach(([x, y], index) => {
    const px = x * rect.width
    const py = y * rect.height
    if (index === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  })
  ctx.stroke()
  if (stroke.points.length === 1) {
    const [x, y] = stroke.points[0]
    ctx.beginPath()
    ctx.arc(x * rect.width, y * rect.height, Math.max(1, Number(stroke.width || 3) / 2), 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.restore()
}

function redraw() {
  const canvas = canvasRef.value
  const stage = stageRef.value
  if (!canvas || !stage) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const rect = stage.getBoundingClientRect()
  ctx.clearRect(0, 0, rect.width, rect.height)
  imState.whiteboard.strokes.forEach((stroke) => drawStroke(ctx, stroke))
}

function localPoint(event) {
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect || !rect.width || !rect.height) return null
  return [
    Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
  ]
}

function onPointerDown(event) {
  if (event.button !== undefined && event.button !== 0) return
  const point = localPoint(event)
  if (!point) return
  if (stageRef.value?.setPointerCapture) {
    try {
      stageRef.value.setPointerCapture(event.pointerId)
    } catch {
      /* ignore */
    }
  }
  if (tool.value === 'laser') {
    localLaser.value = { x: point[0], y: point[1] }
    sendWhiteboardPointer(point[0], point[1], true)
    return
  }
  drawing = true
  currentStroke = {
    tool: tool.value,
    color: color.value,
    width: Number(width.value) || 4,
    points: [point],
  }
  const ctx = canvasRef.value?.getContext('2d')
  if (ctx) drawStroke(ctx, currentStroke)
}

function onPointerMove(event) {
  const point = localPoint(event)
  if (!point) return
  if (tool.value === 'laser') {
    localLaser.value = { x: point[0], y: point[1] }
    sendWhiteboardPointer(point[0], point[1], true)
    return
  }
  if (!drawing || !currentStroke) return
  currentStroke.points.push(point)
  const ctx = canvasRef.value?.getContext('2d')
  if (ctx) {
    const last = currentStroke.points[currentStroke.points.length - 2]
    const rect = stageRef.value.getBoundingClientRect()
    ctx.save()
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    ctx.globalCompositeOperation = currentStroke.tool === 'eraser' ? 'destination-out' : 'source-over'
    ctx.strokeStyle = currentStroke.color
    ctx.lineWidth = currentStroke.width
    ctx.beginPath()
    ctx.moveTo(last[0] * rect.width, last[1] * rect.height)
    ctx.lineTo(point[0] * rect.width, point[1] * rect.height)
    ctx.stroke()
    ctx.restore()
  }
}

function onPointerUp(event) {
  if (tool.value === 'laser') {
    localLaser.value = null
    sendWhiteboardPointer(0, 0, false)
    return
  }
  if (!drawing || !currentStroke) return
  drawing = false
  const stroke = currentStroke
  currentStroke = null
  if (stageRef.value?.releasePointerCapture) {
    try {
      stageRef.value.releasePointerCapture(event.pointerId)
    } catch {
      /* ignore */
    }
  }
  if (stroke.points.length === 1) stroke.points.push(stroke.points[0])
  if (stroke.points.length < 2) {
    redraw()
    return
  }
  if (!sendWhiteboardStroke(stroke)) {
    ElMessage.warning('白板尚未准备好')
    redraw()
  }
}

function onPointerLeave() {
  if (tool.value === 'laser') {
    localLaser.value = null
    sendWhiteboardPointer(0, 0, false)
  }
}

function handleClear() {
  clearConfirm.value = true
}

function confirmClearWhiteboard() {
  clearConfirm.value = false
  clearWhiteboard()
}

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})
</script>

<style scoped>
:global(.im-wb-color-popper),
:global(.im-wb-width-popper) {
  z-index: 6000 !important;
}

.im-wb-layer {
  position: fixed;
  inset: 0;
  z-index: 5050;
  display: grid;
  place-items: center;
  padding: 26px;
  background: rgba(4, 15, 26, .72);
  backdrop-filter: blur(3px);
}
.im-wb-panel {
  width: min(1280px, 96vw);
  height: min(860px, 92vh);
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid #1d4b64;
  background: linear-gradient(165deg, #09243a, #061523);
  box-shadow: 0 30px 80px rgba(0, 0, 0, .6);
  color: #e8f8ff;
}
.im-wb-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: rgba(11, 41, 60, .92);
  border-bottom: 1px solid #17485e;
  flex-wrap: wrap;
}
.im-wb-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.im-wb-title .el-icon { color: #67e8f9; }
.im-wb-title strong { font-size: 15px; }
.im-wb-group { color: #8fb7c9; font-size: 12px; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.im-wb-tools { display: flex; align-items: center; gap: 8px; margin-left: auto; flex-wrap: wrap; }
.im-wb-width { width: 78px; }
.im-wb-tool-group { display: inline-flex; border: 1px solid #1c4a60; border-radius: 8px; overflow: hidden; }
.im-wb-tool {
  border: 0;
  background: rgba(16, 52, 71, .8);
  color: #bcdcea;
  font-size: 11px;
  padding: 6px 9px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.im-wb-tool + .im-wb-tool { border-left: 1px solid #1c4a60; }
.im-wb-tool:hover { background: rgba(56, 189, 248, .16); }
.im-wb-tool.active { background: #0e5b72; color: #eaffff; }
.im-wb-stage {
  position: relative;
  flex: 1;
  min-height: 0;
  margin: 12px;
  border-radius: 12px;
  overflow: hidden;
  touch-action: none;
  cursor: crosshair;
  background-color: #f8fafc;
  background-image:
    linear-gradient(rgba(148, 163, 184, .22) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, .22) 1px, transparent 1px);
  background-size: 28px 28px;
  border: 1px solid #1d4b64;
}
.im-wb-canvas { display: block; width: 100%; height: 100%; }
.im-wb-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #94a3b8;
  pointer-events: none;
  text-align: center;
}
.im-wb-empty strong { color: #475569; font-size: 15px; }
.im-wb-empty span { font-size: 12px; }
.im-wb-hint {
  position: absolute;
  left: 12px;
  bottom: 10px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(15, 23, 42, .55);
  color: #cbd5e1;
  font-size: 10px;
  pointer-events: none;
}
.im-wb-pointer {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  pointer-events: none;
  transition: left .06s linear, top .06s linear;
}
.im-wb-pointer i {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #f472b6;
  border: 2px solid #fff;
  box-shadow: 0 0 10px rgba(244, 114, 182, .8);
}
.im-wb-pointer.is-local i {
  background: #fde047;
  border-color: #fff;
  box-shadow: 0 0 12px rgba(253, 224, 71, .95);
}
.im-wb-pointer em {
  font-style: normal;
  font-size: 10px;
  color: #0f172a;
  background: rgba(255, 255, 255, .85);
  border-radius: 4px;
  padding: 1px 4px;
  white-space: nowrap;
}
.im-wb-clear-confirm {
  position: absolute;
  left: 50%;
  bottom: 18px;
  z-index: 5;
  width: min(620px, calc(100% - 32px));
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 12px;
  border: 1px solid #f3b4b4;
  border-radius: 9px;
  background: #fff7f7;
  box-shadow: 0 8px 28px rgba(15, 23, 42, .22);
  color: #9f2424;
  font-size: 12px;
  line-height: 1.5;
}
.im-wb-clear-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.im-wb-clear-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.im-wb-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 16px 12px;
  color: #7fa6b8;
  font-size: 11px;
}
@media (max-width: 760px) {
  .im-wb-layer { padding: 8px; }
  .im-wb-panel { width: 100vw; height: 94vh; }
  .im-wb-title .im-wb-group { display: none; }
  .im-wb-tools { gap: 5px; }
  .im-wb-foot span:last-child { display: none; }
}
</style>
