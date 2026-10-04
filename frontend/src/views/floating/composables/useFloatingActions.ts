import type { Ref } from 'vue'
// 悬浮球交互域：拖拽 pointer 手势 + 球点击/收起/退出/固定（卷190-B1：从 FloatingView.vue 纯搬移）
import type { FloatingState } from '@/electron.d'
import { ref } from 'vue'
import { CONFIG } from '@/utils/config'

interface DragDeps {
  floatingState: Ref<FloatingState>
  isNotifying: Ref<boolean>
  hasMessages: Ref<boolean>
  setDraggingWindow: (v: boolean) => void
  requestFitHeight: () => void
  stopNotification: () => void
}

export function useFloatingActions(deps: DragDeps) {
  const { floatingState, isNotifying, hasMessages, setDraggingWindow, requestFitHeight, stopNotification } = deps

  const isPinned = ref(false)

  // 悬浮球操作：根据消息历史决定展开目标
  function handleBallClick() {
    if (isNotifying.value) {
      stopNotification()
    }
    window.electronAPI?.floating.expand(hasMessages.value)
  }

  // 手动拖拽实现（-webkit-app-region: drag 会吞掉点击事件，因此所有状态统一用 JS 实现）
  const DRAG_THRESHOLD = 4
  let dragState: { screenX: number, screenY: number, winX: number, winY: number } | null = null
  let hasDragged = false

  function onDragPointerDown(e: PointerEvent) {
    setDraggingWindow(true)
    dragState = {
      screenX: e.screenX,
      screenY: e.screenY,
      winX: e.screenX - e.clientX,
      winY: e.screenY - e.clientY,
    }
    hasDragged = false
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }

  function onDragPointerMove(e: PointerEvent) {
    if (!dragState)
      return
    const dx = e.screenX - dragState.screenX
    const dy = e.screenY - dragState.screenY
    if (!hasDragged && Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD)
      return
    hasDragged = true
    window.electronAPI?.floating.setPosition(dragState.winX + dx, dragState.winY + dy)
  }

  function onDragPointerUp(e: PointerEvent) {
    if (!dragState) {
      setDraggingWindow(false)
      return
    }
    ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
    const moved = hasDragged
    dragState = null
    setDraggingWindow(false)
    if (moved)
      requestFitHeight()
  }

  // 球态：拖拽 + 点击展开（pointerup 需要区分拖拽和点击）
  function onBallPointerUp(e: PointerEvent) {
    if (!dragState) {
      setDraggingWindow(false)
      return
    }
    ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
    const moved = hasDragged
    if (!moved) {
      handleBallClick()
    }
    dragState = null
    setDraggingWindow(false)
    if (moved)
      requestFitHeight()
  }

  // 紧凑态/完整态球：拖拽 + 点击收起
  function onCompactBallPointerDown(e: PointerEvent) {
    e.stopPropagation()
    onDragPointerDown(e)
  }

  function onCompactBallPointerUp(e: PointerEvent) {
    if (!dragState) {
      setDraggingWindow(false)
      return
    }
    ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
    const moved = hasDragged
    if (!moved) {
      handleCollapse()
    }
    dragState = null
    setDraggingWindow(false)
    if (moved)
      requestFitHeight()
  }

  function handleCollapse() {
    window.electronAPI?.floating.collapse()
  }

  function handleExitFloating() {
    CONFIG.value.floating.enabled = false
    window.electronAPI?.floating.exit()
  }

  function togglePin() {
    isPinned.value = !isPinned.value
    window.electronAPI?.floating.pin(isPinned.value)
  }

  // 右键菜单（通过 Electron 原生菜单实现，避免小窗口裁剪）
  function showBallContextMenu(e: MouseEvent) {
    e.preventDefault()
    window.electronAPI?.showContextMenu()
  }

  return {
    isPinned,
    floatingState,
    onDragPointerDown,
    onDragPointerMove,
    onDragPointerUp,
    onBallPointerUp,
    onCompactBallPointerDown,
    onCompactBallPointerUp,
    handleBallClick,
    handleCollapse,
    handleExitFloating,
    togglePin,
    showBallContextMenu,
  }
}
