<!-- 悬浮球壳（卷190-B1：逻辑拆至 floating/composables/*，面板拆至 floating/ 子组件；纯搬移，行为零变化） -->
<script setup lang="ts">
import type { FloatingState } from '@/electron.d'
import { useEventListener } from '@vueuse/core'
import ScrollPanel from 'primevue/scrollpanel'
import { computed, nextTick, onMounted, onUnmounted, ref, useTemplateRef } from 'vue'
import MessageItem from '@/components/MessageItem.vue'
import { toolMessage } from '@/composables/useToolStatus'
import { CURRENT_SESSION_ID, loadCurrentSession, MESSAGES } from '@/utils/session'
import { useBallAnimation } from './floating/composables/useBallAnimation'
import { useFloatingActions } from './floating/composables/useFloatingActions'
import { useFloatingChat } from './floating/composables/useFloatingChat'
import { useFloatingFit } from './floating/composables/useFloatingFit'
import FloatingBall from './floating/FloatingBall.vue'
import FloatingCapturePanel from './floating/FloatingCapturePanel.vue'
import FloatingCompact from './floating/FloatingCompact.vue'
import FloatingSessionsPanel from './floating/FloatingSessionsPanel.vue'

// ── 模板引用 ──
const inputRef = useTemplateRef<HTMLInputElement>('inputRef')
const scrollPanelRef = useTemplateRef<{ scrollTop: (v: number) => void }>('scrollPanelRef')
const messageContentRef = useTemplateRef<HTMLElement>('messageContentRef')
const fileInputRef = useTemplateRef<HTMLInputElement>('fileInputRef')
// 两个面板子组件 defineExpose({ rootEl })：fitWindowHeight 需测量面板展开高度
const sessionPanelRef = useTemplateRef<{ rootEl: HTMLElement }>('sessionPanelRef')
const capturePanelRef = useTemplateRef<{ rootEl: HTMLElement }>('capturePanelRef')

// ── 跨域共享状态 ──
const floatingState = ref<FloatingState>('ball')
const showContent = ref(false) // 控制内容入场动画
const showHistory = ref(false)
const showCapturePanel = ref(false)

// 是否有消息历史（用于决定展开到 compact 还是 full）
const hasMessages = computed(() => MESSAGES.value.length > 0)

// 判断当前是否处于展开状态（compact 或 full）
const isExpanded = computed(() =>
  floatingState.value === 'compact' || floatingState.value === 'full',
)

// 是否正在生成回复（用于光晕脉冲特效）
const isGenerating = computed(() => MESSAGES.value.at(-1)?.generating === true)

// ── 领域组装（依赖方向：fit ← actions ← chat，均只依赖更底层，无环） ──
const fit = useFloatingFit({
  floatingState,
  messageContentRef,
  sessionPanelRef,
  capturePanelRef,
  showHistory,
  showCapturePanel,
})

const ball = useBallAnimation(floatingState)

const actions = useFloatingActions({
  floatingState,
  isNotifying: ball.isNotifying,
  hasMessages,
  setDraggingWindow: fit.setDraggingWindow,
  requestFitHeight: fit.requestFitHeight,
  stopNotification: ball.stopNotification,
})

const chat = useFloatingChat({
  floatingState,
  inputRef,
  scrollPanelRef,
  fileInputRef,
  showCapturePanel,
  showHistory,
  fitWindowHeight: fit.fitWindowHeight,
  setupResizeObserver: fit.setupResizeObserver,
})

const {
  isDraggingWindow,
  setDraggingWindow,
  requestFitHeight,
  setupResizeObserver,
  teardownResizeObserver,
} = fit
const { frameIndex, isNotifying, showLightbulb, startFrameAnimation, stopFrameAnimation, stopNotification } = ball
const { onDragPointerDown, onDragPointerMove, onDragPointerUp, onBallPointerUp, onCompactBallPointerDown, onCompactBallPointerUp, handleCollapse, handleExitFloating, togglePin, showBallContextMenu } = actions
const {
  input,
  scrollToBottom,
  QUICK_SKILLS,
  activeSkillIndex,
  handleQuickSkill,
  pendingImages,
  handleCapture,
  closeCapturePanel,
  openScreenSettings,
  selectCaptureSource,
  removePendingImage,
  handleKeydown,
  triggerFileUpload,
  handleFileUpload,
  handleNewSession,
  handleNewTemporarySession,
  sessions,
  loadingSessions,
  toggleHistory,
  closeHistory,
  handleSwitchSession,
  handleDeleteSession,
  getSuppressBlur,
} = chat

onMounted(() => {
  const api = window.electronAPI
  if (!api)
    return

  // 启动序列帧动画
  startFrameAnimation()

  // 加载会话
  loadCurrentSession()

  // 获取初始状态
  api.floating.getState().then((state) => {
    floatingState.value = state
  })

  // 监听状态变化
  const unsubStateChange = api.floating.onStateChange((state) => {
    floatingState.value = state
    if (state === 'compact' || state === 'full') {
      // 延迟触发内容入场动画（等窗口动画结束）
      showContent.value = false
      nextTick().then(() => {
        showContent.value = true
        if (state === 'full') {
          nextTick().then(() => {
            scrollToBottom()
            setupResizeObserver()
            requestFitHeight()
          })
        }
        // 自动聚焦输入框
        setTimeout(() => {
          inputRef.value?.focus()
        }, 100)
      })
    }
    else {
      showContent.value = false
      teardownResizeObserver()
    }
  })

  // 监听窗口失焦
  const unsubBlur = api.floating.onWindowBlur(() => {
    if (isExpanded.value && !actions.isPinned.value && !getSuppressBlur()) {
      api.floating.collapse()
    }
  })

  onUnmounted(() => {
    unsubStateChange?.()
    unsubBlur?.()
  })
})

onUnmounted(() => {
  // 恢复经典模式背景
  document.documentElement.style.backgroundColor = '#0e1116'
  stopFrameAnimation()
  stopNotification()
})

// Esc 键：收起窗口
useEventListener('keydown', (e: KeyboardEvent) => {
  if (e.key === 'Escape' && isExpanded.value) {
    handleCollapse()
  }
})

// 监听新消息到达时的自动滚动和高度调整
useEventListener('token', () => {
  scrollToBottom()
  requestFitHeight()
})

// 供模板的落屏前清空（保持 v-model 双向）
function onRemoveImage(idx: number) {
  removePendingImage(idx)
}

void isDraggingWindow
void setDraggingWindow
</script>

<template>
  <!-- 球态：序列帧动画悬浮球（拖拽/点击/右键由 attrs fallthrough 绑到根元素） -->
  <FloatingBall
    v-if="floatingState === 'ball'"
    :frame-index="frameIndex"
    :generating="isGenerating"
    :notifying="isNotifying"
    :lightbulb="showLightbulb"
    @pointerdown="onDragPointerDown"
    @pointermove="onDragPointerMove"
    @pointerup="onBallPointerUp"
    @contextmenu.prevent="showBallContextMenu"
  />

  <!-- 紧凑态：方块头像 + 标语 + 输入框（Everywhere 风格） -->
  <FloatingCompact
    v-else-if="floatingState === 'compact'"
    v-model="input"
    :frame-index="frameIndex"
    :skills="QUICK_SKILLS"
    :active-skill-index="activeSkillIndex"
    :pending-images="pendingImages"
    :show-capture-panel="showCapturePanel"
    :has-messages="hasMessages"
    :show-content="showContent"
    :is-pinned="actions.isPinned.value"
    variant="compact"
    @ball-pointer-down="onCompactBallPointerDown"
    @ball-pointer-move="onDragPointerMove"
    @ball-pointer-up="onCompactBallPointerUp"
    @pointerdown="onDragPointerDown"
    @pointermove="onDragPointerMove"
    @pointerup="onDragPointerUp"
    @quick-skill="handleQuickSkill"
    @remove-image="onRemoveImage"
    @new-temporary="handleNewTemporarySession"
    @toggle-history="toggleHistory"
    @toggle-pin="togglePin"
    @exit-floating="handleExitFloating"
    @collapse="handleCollapse"
    @new-session="handleNewSession"
    @capture="handleCapture"
    @file-upload-click="triggerFileUpload"
    @keydown="handleKeydown"
  />

  <!-- 完整态：输入框在上 + 消息在下（自适应高度） -->
  <div v-else-if="floatingState === 'full'" class="floating-full">
    <!-- 顶部栏：与紧凑态相同的头像+输入区（FloatingCompact variant=full） -->
    <FloatingCompact
      v-model="input"
      :frame-index="frameIndex"
      :skills="QUICK_SKILLS"
      :active-skill-index="activeSkillIndex"
      :pending-images="pendingImages"
      :show-capture-panel="showCapturePanel"
      :has-messages="hasMessages"
      :show-content="false"
      :is-pinned="actions.isPinned.value"
      variant="full"
      class="compact-header"
      @ball-pointer-down="onCompactBallPointerDown"
      @ball-pointer-move="onDragPointerMove"
      @ball-pointer-up="onCompactBallPointerUp"
      @pointerdown="onDragPointerDown"
      @pointermove="onDragPointerMove"
      @pointerup="onDragPointerUp"
      @quick-skill="handleQuickSkill"
      @remove-image="onRemoveImage"
      @new-temporary="handleNewTemporarySession"
      @toggle-history="toggleHistory"
      @toggle-pin="togglePin"
      @exit-floating="handleExitFloating"
      @collapse="handleCollapse"
      @new-session="handleNewSession"
      @capture="handleCapture"
      @file-upload-click="triggerFileUpload"
      @keydown="handleKeydown"
    />

    <!-- 会话历史面板 -->
    <FloatingSessionsPanel
      ref="sessionPanelRef"
      :open="showHistory"
      :sessions="sessions"
      :loading="loadingSessions"
      :current-session-id="CURRENT_SESSION_ID"
      @close="closeHistory"
      @switch="handleSwitchSession"
      @delete="handleDeleteSession"
    />

    <!-- 窗口截屏选择面板 -->
    <FloatingCapturePanel
      ref="capturePanelRef"
      :open="showCapturePanel"
      :sources="chat.captureSources.value"
      :loading="chat.loadingCapture.value"
      :permission-denied="chat.capturePermissionDenied.value"
      @close="closeCapturePanel"
      @select="selectCaptureSource"
      @open-settings="openScreenSettings"
    />

    <!-- 消息区域 -->
    <ScrollPanel
      ref="scrollPanelRef"
      class="w-full flex-1 min-h-0 border-t border-white/6"
      :class="{ 'enter-anim': showContent }"
      :pt="{ barY: { class: 'w-2! rounded! bg-#373737! transition!' } }"
    >
      <div ref="messageContentRef" class="p-3 grid gap-3 overflow-x-hidden">
        <MessageItem
          v-for="item, index in MESSAGES" :key="index"
          :role="item.role" :content="item.content"
          :reasoning="item.reasoning" :sender="item.sender"
          :generating="item.generating" :status="item.status"
          :class="(item.generating && index === MESSAGES.length - 1) || 'border-b border-white/6'"
        />
      </div>
    </ScrollPanel>

    <!-- 工具状态提示 -->
    <Transition name="session-fade">
      <div v-if="toolMessage" class="text-white/50 text-xs px-3 py-1 shrink-0 border-t border-white/6">
        {{ toolMessage }}
      </div>
    </Transition>
  </div>

  <!-- 隐藏的文件上传 input -->
  <input
    ref="fileInputRef"
    type="file"
    accept=".docx,.xlsx,.txt,.csv,.md,.pdf,.png,.jpg,.jpeg,.gif,.webp"
    class="hidden"
    @change="handleFileUpload"
  >
</template>

<style scoped>
/* ========== 完整态容器（球态/紧凑态样式随各自子组件） ========== */
.floating-full {
  width: 100%;
  height: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  background: #0e1116;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

/* full 态顶栏尺寸（FloatingCompact variant=full 的根即此栏） */
.compact-header {
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
  height: 100px;
  max-height: 100px;
  overflow: hidden;
}

/* ========== 内容入场动画（full 态 ScrollPanel 用；compact 内的同名样式在子组件） ========== */
@keyframes enter-fade-up {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.enter-anim {
  animation: enter-fade-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

/* ========== 工具状态提示过渡（与子面板的 session-fade 同名同参数） ========== */
.session-fade-enter-active {
  transition: opacity 0.15s ease;
}

.session-fade-leave-active {
  transition: opacity 0.1s ease;
}

.session-fade-enter-from,
.session-fade-leave-to {
  opacity: 0;
}
</style>
