// 输入区/composer 域：输入框自适应高度 + 放大布局 + TTS 开关（卷190-B3：从 MessageView.vue setup 纯搬移）
import type { Ref } from 'vue'
import { useEventListener } from '@vueuse/core'
import { computed, nextTick, ref, watch } from 'vue'
import { CONFIG } from '@/utils/config'
import { live2dState } from '@/utils/live2dController'
import { isPlaying, stop as stopTTS } from '@/utils/tts'
import { setMessageViewExpanded } from '@/utils/uiState'

export interface ComposerRefs {
  normalContainerRef: Ref<any>
  expandedContainerRef: Ref<any>
}

export function useComposer(refs: ComposerRefs) {
  const { normalContainerRef, expandedContainerRef } = refs

  const composerRef = ref<HTMLTextAreaElement | null>(null)
  const inputDockRef = ref<HTMLElement | null>(null)
  const isExpanded = ref(false)
  const expandedStyle = ref<Record<string, string>>({})
  const expandedInputStyle = ref<Record<string, string>>({})
  const expandedAnchorLeft = ref(8)

  function isImeComposing(event: KeyboardEvent) {
    return event.isComposing || (event as any).keyCode === 229
  }

  function resizeComposer() {
    if (!composerRef.value) {
      return
    }
    composerRef.value.style.height = '0px'
    const nextHeight = Math.min(Math.max(composerRef.value.scrollHeight, 44), 160)
    composerRef.value.style.height = `${nextHeight}px`
  }

  function updateExpandedLayout() {
    if (!inputDockRef.value) {
      return
    }
    const chatRect = (normalContainerRef.value as any)?.$el?.getBoundingClientRect?.()
    const inputRect = inputDockRef.value.getBoundingClientRect()
    const left = isExpanded.value
      ? expandedAnchorLeft.value
      : Math.max(8, chatRect?.left ?? expandedAnchorLeft.value)
    const composerHeight = Math.max(56, Math.ceil(inputRect.height))
    expandedStyle.value = {
      left: `${left}px`,
      top: '8px',
      right: '8px',
      bottom: `${composerHeight + 16}px`,
    }
    expandedInputStyle.value = {
      left: `${left}px`,
      right: '8px',
      bottom: '8px',
    }
  }

  function scrollToBottom() {
    normalContainerRef.value?.scrollToBottom()
    expandedContainerRef.value?.scrollToBottom()
  }

  // 用户向上翻阅历史时不抢滚动：只有当前活跃容器停留在底部附近才跟随。
  function scrollToBottomIfPinned() {
    const active = isExpanded.value ? expandedContainerRef.value : normalContainerRef.value
    if (active?.isNearBottom(96))
      scrollToBottom()
  }

  function toggleExpanded() {
    if (!isExpanded.value) {
      const chatRect = (normalContainerRef.value as any)?.$el?.getBoundingClientRect?.()
      if (chatRect) {
        expandedAnchorLeft.value = Math.max(8, chatRect.left)
      }
    }
    isExpanded.value = !isExpanded.value
    nextTick(() => {
      resizeComposer()
      if (isExpanded.value) {
        updateExpandedLayout()
        nextTick().then(scrollToBottom)
      }
    })
  }

  function toggleTTS() {
    CONFIG.value.system.voice_enabled = !CONFIG.value.system.voice_enabled
    if (!CONFIG.value.system.voice_enabled) {
      stopTTS() // 关闭时停止当前播放
    }
  }

  // TTS 播放状态驱动嘴部动画：开始播放→talking，结束→idle
  watch(isPlaying, (playing) => {
    live2dState.value = playing ? 'talking' : 'idle'
  })

  watch(isExpanded, (value) => {
    setMessageViewExpanded(value)
  })

  useEventListener('token', scrollToBottomIfPinned)
  useEventListener(window, 'resize', () => {
    if (isExpanded.value) {
      updateExpandedLayout()
    }
  })

  return {
    composerRef,
    inputDockRef,
    isExpanded,
    expandedStyle,
    expandedInputStyle,
    isImeComposing,
    resizeComposer,
    updateExpandedLayout,
    scrollToBottom,
    scrollToBottomIfPinned,
    toggleExpanded,
    toggleTTS,
  }
}

export const ttsEnabled = computed(() => CONFIG.value.system.voice_enabled)
