<template>
  <div
    ref="rootRef"
    class="bs3-auto-scroll"
    :class="{ 'is-reduced': reduceMotion, 'is-paused': paused }"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
    @touchstart.passive="paused = true"
    @touchend="paused = false"
    @touchcancel="paused = false"
    @focusin="paused = true"
    @focusout="paused = false"
  >
    <slot />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 大屏内容自动缓慢滚动。
 *
 * - 仅当内容高度超过容器时才滚动，内容不足时自动复位到顶部；
 * - 鼠标悬停 / 触摸 / 键盘聚焦时暂停，移出后继续；
 * - 滚动到底部后停留 pauseMs，再回到顶部重新开始（缓慢循环）；
 * - 尊重 prefers-reduced-motion：开启减少动态效果时完全不自动滚动，
 *   仅保留浏览器原生手动滚动，并显示细滚动条。
 */
const props = defineProps({
  /** 滚动速度，单位 px/s */
  speed: { type: Number, default: 12 },
  /** 滚动到底部后的停留时间，单位 ms */
  pauseMs: { type: Number, default: 1400 },
})

const rootRef = ref(null)
const paused = ref(false)
const reduceMotion = ref(false)

let rafId = null
let lastTs = 0
let accumulated = 0
let resumeTimer = null
let observer = null
let mediaQuery = null

function syncReduceMotion(event) {
  reduceMotion.value = Boolean(event?.matches)
  if (reduceMotion.value && resumeTimer) {
    window.clearTimeout(resumeTimer)
    resumeTimer = null
  }
}

function canScroll() {
  const root = rootRef.value
  return Boolean(root && root.scrollHeight > root.clientHeight + 2)
}

function maxScrollTop() {
  const root = rootRef.value
  return root ? Math.max(0, root.scrollHeight - root.clientHeight) : 0
}

function shouldMove() {
  return !reduceMotion.value && !paused.value && !document.hidden && !resumeTimer
}

function tick(ts) {
  rafId = window.requestAnimationFrame(tick)
  const root = rootRef.value
  if (!root) {
    lastTs = ts
    return
  }

  // 减少动态效果 / 悬停 / 后台标签页：停止滚动但不改变用户当前位置
  if (!shouldMove()) {
    lastTs = ts
    accumulated = 0
    return
  }

  const maxTop = maxScrollTop()
  if (maxTop <= 2) {
    if (root.scrollTop) root.scrollTop = 0
    lastTs = ts
    accumulated = 0
    return
  }

  if (!lastTs) lastTs = ts
  const delta = Math.min(120, Math.max(0, ts - lastTs))
  lastTs = ts

  if (root.scrollTop >= maxTop - 0.5) {
    // 到底后停留一段时间，再回到顶部循环
    resumeTimer = window.setTimeout(() => {
      resumeTimer = null
      if (!shouldMove() || !canScroll()) return
      if (rootRef.value) rootRef.value.scrollTop = 0
      lastTs = 0
      accumulated = 0
    }, Math.max(300, Number(props.pauseMs) || 1400))
    return
  }

  accumulated += (Math.max(1, Number(props.speed) || 12) * delta) / 1000
  // 累积到亚像素级再写入，避免低速度下每帧取整造成抖动
  if (accumulated >= 0.25) {
    root.scrollTop = Math.min(maxTop, root.scrollTop + accumulated)
    accumulated = 0
  }
}

function measure() {
  const root = rootRef.value
  if (!root) return
  if (!canScroll() && root.scrollTop) root.scrollTop = 0
}

onMounted(() => {
  if (typeof window.matchMedia === 'function') {
    mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    reduceMotion.value = mediaQuery.matches
    if (mediaQuery.addEventListener) mediaQuery.addEventListener('change', syncReduceMotion)
    else mediaQuery.addListener?.(syncReduceMotion)
  }
  measure()
  if (typeof ResizeObserver !== 'undefined' && rootRef.value) {
    observer = new ResizeObserver(measure)
    observer.observe(rootRef.value)
  }
  rafId = window.requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  if (rafId) window.cancelAnimationFrame(rafId)
  if (resumeTimer) window.clearTimeout(resumeTimer)
  if (mediaQuery?.removeEventListener) mediaQuery.removeEventListener('change', syncReduceMotion)
  else mediaQuery?.removeListener?.(syncReduceMotion)
  observer?.disconnect()
  rafId = null
  resumeTimer = null
  observer = null
  mediaQuery = null
})
</script>

<style scoped>
.bs3-auto-scroll {
  height: 100%;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.bs3-auto-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}

/* 减少动态效果：不自动滚动，显示细滚动条供手动浏览 */
.bs3-auto-scroll.is-reduced {
  scrollbar-width: thin;
  scrollbar-color: rgba(56, 189, 248, 0.4) transparent;
}

.bs3-auto-scroll.is-reduced::-webkit-scrollbar {
  display: block;
  width: 5px;
  height: 5px;
}

.bs3-auto-scroll.is-reduced::-webkit-scrollbar-thumb {
  border-radius: 3px;
  background: rgba(56, 189, 248, 0.4);
}

.bs3-auto-scroll.is-reduced::-webkit-scrollbar-track {
  background: transparent;
}

.bs3-auto-scroll :deep(.bs3-table thead) {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #04121f;
}
</style>
