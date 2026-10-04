// 拖动横向/纵向滚动通用工具（卷190-B2：从 MarketView.vue 纯搬移）
// wasDragging 为模块级单例：拖拽与点击的竞争判断（toggleCard/handleBgAction 都要查它）
import { ref } from 'vue'

const DRAG_THRESHOLD = 4

/** 全局「刚拖拽过」标记：拖拽手势结束后短暂为 true，用于屏蔽点击 */
export const wasDragging = ref(false)

// 组件卸载时若仍处于拖动中，收掉 document 级监听（正常 mouseup 时 onUp 已自清理）
let activeDragCleanup: (() => void) | null = null

export function disposeActiveDrag() {
  activeDragCleanup?.()
  activeDragCleanup = null
}

export function initDragScroll(container: HTMLElement) {
  container.addEventListener('mousedown', (e: MouseEvent) => {
    const startX = e.clientX
    const startScrollLeft = container.scrollLeft
    let moved = false

    container.style.cursor = 'grabbing'
    document.body.style.cursor = 'grabbing'

    function onMove(ev: MouseEvent) {
      const dx = ev.clientX - startX
      if (Math.abs(dx) > DRAG_THRESHOLD)
        moved = true
      container.scrollLeft = startScrollLeft - dx
    }

    function onUp() {
      wasDragging.value = moved
      container.style.cursor = 'grab'
      document.body.style.cursor = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      // 在 click 事件触发后再重置标记
      setTimeout(() => {
        wasDragging.value = false
      }, 0)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    activeDragCleanup = onUp
  })

  container.addEventListener('wheel', (e: WheelEvent) => {
    e.preventDefault()
    container.scrollLeft += e.deltaY
  }, { passive: false })
}

// 背景网格垂直拖动滚动
export function initVerticalDragScroll(container: HTMLElement) {
  let wasSkinDragging = false

  container.addEventListener('mousedown', (e: MouseEvent) => {
    const startY = e.clientY
    const startScrollTop = container.scrollTop
    let moved = false

    container.style.cursor = 'grabbing'
    document.body.style.cursor = 'grabbing'

    function onMove(ev: MouseEvent) {
      const dy = ev.clientY - startY
      if (Math.abs(dy) > DRAG_THRESHOLD)
        moved = true
      container.scrollTop = startScrollTop - dy
    }

    function onUp() {
      wasSkinDragging = moved
      container.style.cursor = ''
      document.body.style.cursor = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      setTimeout(() => {
        wasSkinDragging = false
      }, 0)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    activeDragCleanup = onUp
  })

  // 拦截点击，拖动中不触发 handleBgAction
  container.addEventListener('click', (e: MouseEvent) => {
    if (wasSkinDragging) {
      e.stopPropagation()
      e.preventDefault()
    }
  }, true)
}
