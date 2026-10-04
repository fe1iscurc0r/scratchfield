import type { Ref } from 'vue'
// 悬浮窗布局域：fitHeight 自适应 + ResizeObserver + 拖拽冻结通知 + 背景色（卷190-B1：从 FloatingView.vue 纯搬移）
// 生命周期编排留在壳（onMounted 里的启动顺序跨域，保持原顺序 = 行为零变化）
import type { FloatingState } from '@/electron.d'
import { onUnmounted, ref, watch } from 'vue'
import { toolMessage } from '@/composables/useToolStatus'

interface FitRefs {
  floatingState: Ref<FloatingState>
  messageContentRef: Ref<HTMLElement | null>
  sessionPanelRef: { readonly value: { rootEl: HTMLElement } | null }
  capturePanelRef: { readonly value: { rootEl: HTMLElement } | null }
  showHistory: Ref<boolean>
  showCapturePanel: Ref<boolean>
}

export function useFloatingFit(refs: FitRefs) {
  const { floatingState, messageContentRef, sessionPanelRef, capturePanelRef, showHistory, showCapturePanel } = refs

  let resizeObserver: ResizeObserver | null = null
  let fitRAF = 0
  let _lastFitHeight = 0 // 防止 ResizeObserver 反馈循环
  const isDraggingWindow = ref(false)
  // ★ 卷149：fitHeight 趋势守卫计数（_lastFitHeight 只挡"相同值"，挡不住递增环）
  let fitRisingStreak = 0
  const FIT_RISING_LIMIT = 5

  /**
   * 拖拽状态切换（卷149）。
   *
   * 渲染层用 isDraggingWindow 抑制自己的 fitWindowHeight；
   * 同时**必须通知主进程** —— 按"渲染层不可信原则"，主进程要独立冻结尺寸变更，
   * 否则拖拽手势会与 fitHeight / 尺寸纠正竞争，造成抖动与"被撑大"。
   */
  function setDraggingWindow(value: boolean) {
    isDraggingWindow.value = value
    if (!value)
      fitRisingStreak = 0 // 一次拖拽会话结束，趋势历史清零
    window.electronAPI?.floating.setDragging(value)
  }

  // 根据消息内容自适应窗口高度
  function fitWindowHeight() {
    if (floatingState.value !== 'full')
      return
    if (isDraggingWindow.value)
      return
    const el = messageContentRef.value
    if (!el)
      return
    const HEADER_HEIGHT = 100
    const BORDER = 2
    const toolH = toolMessage.value ? 24 : 0
    // 使用 showHistory 守卫：Transition leave 期间 DOM 元素仍在但 showHistory 已为 false，避免误计
    const sessionH = showHistory.value ? (sessionPanelRef.value?.rootEl.offsetHeight ?? 0) : 0
    const captureH = showCapturePanel.value ? (capturePanelRef.value?.rootEl.offsetHeight ?? 0) : 0
    const contentH = el.scrollHeight
    const desired = HEADER_HEIGHT + sessionH + captureH + contentH + toolH + BORDER
    // 高度未变化时跳过，打断 ResizeObserver → fitHeight → resize → observer 的反馈循环
    if (desired === _lastFitHeight)
      return

    // ★ 卷149：趋势守卫。
    // 若测量容器的高度随窗口变大而变大（flex/overflow 依赖视口），会形成
    // "窗口变大 → scrollHeight 变大 → desired 变大 → 窗口再变大"的**递增环**，
    // 上面的"相同值"守卫对它无效。故按连续递增次数判定。
    fitRisingStreak = desired > _lastFitHeight ? fitRisingStreak + 1 : 0

    if (fitRisingStreak >= FIT_RISING_LIMIT) {
      console.warn(
        `[floating] fitHeight 连续递增 ${fitRisingStreak} 次，判定反馈环，本次拟合已忽略（desired=${desired}）`,
      )
      fitRisingStreak = 0 // 判环即归零，避免用户真实连续输入被永久拒绝
      _lastFitHeight = desired
      return
    }

    _lastFitHeight = desired
    window.electronAPI?.floating.fitHeight(desired)
  }

  function requestFitHeight() {
    if (fitRAF)
      return
    fitRAF = requestAnimationFrame(() => {
      fitRAF = 0
      fitWindowHeight()
    })
  }

  function setupResizeObserver() {
    resizeObserver?.disconnect()
    if (messageContentRef.value) {
      resizeObserver = new ResizeObserver(requestFitHeight)
      resizeObserver.observe(messageContentRef.value)
    }
  }

  function teardownResizeObserver() {
    resizeObserver?.disconnect()
    resizeObserver = null
  }

  // 球态下让 Electron 透明窗口无方形背景，展开态恢复不透明
  watch(floatingState, (state) => {
    const bg = state === 'ball' ? 'transparent' : '#0e1116'
    document.documentElement.style.backgroundColor = bg
  }, { immediate: true })

  onUnmounted(() => {
    // 卸载时若仍处拖拽态，解除主进程的尺寸冻结（防御：避免冻结状态泄漏）
    if (isDraggingWindow.value)
      window.electronAPI?.floating.setDragging(false)
    resizeObserver?.disconnect()
    if (fitRAF) {
      cancelAnimationFrame(fitRAF)
      fitRAF = 0
    }
  })

  return {
    isDraggingWindow,
    setDraggingWindow,
    fitWindowHeight,
    requestFitHeight,
    setupResizeObserver,
    teardownResizeObserver,
  }
}
