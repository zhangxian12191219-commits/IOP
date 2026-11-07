import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 响应式表格断点：
 * - tablet: < 1500px，隐藏次要列
 * - compact: < 1200px，再隐藏次要列/切换紧凑展示
 */
export function useResponsiveViewport() {
  const width = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)

  function update() {
    width.value = window.innerWidth
  }

  onMounted(() => window.addEventListener('resize', update, { passive: true }))
  onBeforeUnmount(() => window.removeEventListener('resize', update))

  return {
    viewportWidth: width,
    isTablet: computed(() => width.value < 1500),
    isCompact: computed(() => width.value < 1200),
  }
}
