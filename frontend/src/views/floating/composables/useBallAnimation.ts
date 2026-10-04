import type { Ref } from 'vue'
// 悬浮球外观：序列帧眨眼动画 + 生成完成灯泡通知（卷190-B1：从 FloatingView.vue 纯搬移）
import type { FloatingState } from '@/electron.d'
import { ref, watch } from 'vue'
import { MESSAGES } from '@/utils/session'

export function useBallAnimation(floatingState: Ref<FloatingState>) {
  // 序列帧动画（球态）
  const frameIndex = ref(1) // 默认显示帧1（睁眼）
  const framePath = (i: number) => `./assets/悬浮球序列帧/${i}.png`
  let blinkTimer: ReturnType<typeof setTimeout> | null = null
  let blinkStopped = false // 用于终止正在进行的眨眼序列

  // 眨眼动画序列：睁眼->半闭->闭眼->半闭->睁眼
  const BLINK_SEQUENCE = [1, 2, 3, 4, 5, 4, 3, 2, 1]
  const BLINK_FRAME_MS = 70

  function playBlink() {
    let step = 0
    const next = () => {
      if (blinkStopped)
        return
      if (step >= BLINK_SEQUENCE.length) {
        // 眨眼结束，随机 2~5 秒后再次眨眼
        scheduleNextBlink()
        return
      }
      frameIndex.value = BLINK_SEQUENCE[step]!
      step++
      setTimeout(next, BLINK_FRAME_MS)
    }
    next()
  }

  function scheduleNextBlink() {
    const delay = 2000 + Math.random() * 3000
    blinkTimer = setTimeout(playBlink, delay)
  }

  function startFrameAnimation() {
    blinkStopped = false
    frameIndex.value = 1
    scheduleNextBlink()
  }

  function stopFrameAnimation() {
    blinkStopped = true
    if (blinkTimer) {
      clearTimeout(blinkTimer)
      blinkTimer = null
    }
  }

  // 生成完成通知（灯泡覆盖层独立闪烁，不影响底层眨眼动画）
  let notifyTimer: ReturnType<typeof setInterval> | null = null
  const isNotifying = ref(false)
  const showLightbulb = ref(false)

  function startNotification() {
    isNotifying.value = true
    showLightbulb.value = true
    notifyTimer = setInterval(() => {
      showLightbulb.value = !showLightbulb.value
    }, 400)
  }

  function stopNotification() {
    if (notifyTimer) {
      clearInterval(notifyTimer)
      notifyTimer = null
    }
    isNotifying.value = false
    showLightbulb.value = false
  }

  // 监听生成完成：generating 从 true 变为 undefined 时，球态下触发灯泡闪烁
  watch(
    () => MESSAGES.value.at(-1)?.generating,
    (curr, prev) => {
      if (prev && !curr && floatingState.value === 'ball') {
        startNotification()
      }
    },
  )

  return {
    frameIndex,
    framePath,
    isNotifying,
    showLightbulb,
    startFrameAnimation,
    stopFrameAnimation,
    startNotification,
    stopNotification,
  }
}
