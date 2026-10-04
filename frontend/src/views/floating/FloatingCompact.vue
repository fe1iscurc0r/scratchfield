<!-- 悬浮球·紧凑态（卷190-B1：从 FloatingView.vue 纯搬移，template+style 同进退）。
     拖拽事件由壳通过 attrs fallthrough 绑到根元素；内部交互按钮 @pointerdown.stop 阻断拖拽。 -->
<script setup lang="ts">
import { useTemplateRef } from 'vue'
import { CONFIG } from '@/utils/config'
import { IS_TEMPORARY_SESSION } from '@/utils/session'

const props = withDefaults(defineProps<{
  frameIndex: number
  skills: Array<{ label: string, name: string }>
  activeSkillIndex: number
  pendingImages: string[]
  showCapturePanel: boolean
  hasMessages: boolean
  showContent: boolean
  isPinned: boolean
  /** compact = 独立紧凑窗；full = 完整态顶栏（标题用 ai_name，输入区加 pointerdown.stop） */
  variant?: 'compact' | 'full'
}>(), { variant: 'compact' })

const emit = defineEmits<{
  /** 左侧方块球的拖拽/点击三件套（handler 在壳的 useFloatingActions） */
  ballPointerDown: [e: PointerEvent]
  ballPointerMove: [e: PointerEvent]
  ballPointerUp: [e: PointerEvent]
  quickSkill: [index: number]
  removeImage: [index: number]
  newTemporary: []
  toggleHistory: []
  togglePin: []
  exitFloating: []
  collapse: []
  newSession: []
  capture: []
  fileUploadClick: []
  keydown: [e: KeyboardEvent]
}>()
const input = defineModel<string>({ default: '' })
const isFull = props.variant === 'full'
// full 态输入区需要 @pointerdown.stop（防拖拽冲突），compact 态原文件没有该监听 ——
// 用动态 v-on 精确还原：stop 修饰符带恒真表达式会改变 compact 行为
const stopPropagation = (e: Event) => e.stopPropagation()
const fullOnlyStop = isFull ? { pointerdown: stopPropagation } : {}

const inputRef = useTemplateRef<HTMLInputElement>('inputRef')
// 壳需要在状态切换后聚焦此输入框
defineExpose({ inputRef })
</script>

<template>
  <div class="floating-compact" @dragstart.prevent>
    <!-- 左侧方块：与球态视觉一致，拖拽移动/点击收起 -->
    <div class="compact-ball" @pointerdown="emit('ballPointerDown', $event)" @pointermove="emit('ballPointerMove', $event)" @pointerup="emit('ballPointerUp', $event)" @dragstart.prevent>
      <div class="ball-content">
        <img :src="`./assets/悬浮球序列帧/${frameIndex}.png`" class="ball-frame" draggable="false">
      </div>
      <div class="ball-ring" />
    </div>
    <!-- 右侧内容（带入场动画） -->
    <div
      class="flex-1 flex flex-col justify-center gap-1 min-w-0 px-4"
      :class="{ 'enter-anim': showContent }"
    >
      <div class="flex items-center gap-1">
        <span class="flex-1 text-white/40 text-xs truncate select-none">{{ isFull ? CONFIG.system.ai_name : '有什么可以帮你的吗？' }}</span>
        <div class="flex items-center shrink-0" @pointerdown.stop>
          <button class="action-btn" :class="{ active: IS_TEMPORARY_SESSION }" title="临时聊天" @click="emit('newTemporary')">🕶</button>
          <button class="action-btn" title="对话历史" @click="emit('toggleHistory')">📋</button>
          <button class="action-btn" :class="{ active: isPinned }" :title="isPinned ? '取消固定' : '固定窗口'" @click="emit('togglePin')">📌</button>
          <button class="action-btn" title="打开主界面" @click="emit('exitFloating')"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg></button>
          <button class="action-btn" title="退出悬浮球" @click="emit('collapse')">✕</button>
        </div>
      </div>
      <div class="flex items-center gap-1 overflow-x-auto" @pointerdown.stop>
        <button
          v-for="skill, idx in skills" :key="skill.label"
          class="skill-tag" :class="{ active: activeSkillIndex === idx }"
          @click="emit('quickSkill', idx)"
        >
          {{ skill.label }}
        </button>
      </div>
      <div v-if="pendingImages.length" class="pending-image-bar" @pointerdown.stop>
        <div v-for="img, idx in pendingImages" :key="idx" class="pending-image-item">
          <img :src="img" class="pending-image-thumb" draggable="false">
          <button class="pending-image-remove" @click="emit('removeImage', idx)">&#x2715;</button>
        </div>
        <span class="text-white/40 text-xs shrink-0">{{ pendingImages.length }}张截图</span>
      </div>
      <div class="flex items-center gap-1" @pointerdown.stop>
        <input
          ref="inputRef"
          v-model="input"
          class="flex-1 text-sm text-white bg-transparent border-none outline-none p-0"
          type="text"
          :placeholder="pendingImages.length ? '输入提示词后回车发送...' : '输入消息...'"
          v-on="fullOnlyStop"
          @keydown="emit('keydown', $event)"
        >
        <button class="action-btn" :class="{ active: showCapturePanel }" title="截屏" @click="emit('capture')">📷</button>
        <button class="action-btn" title="上传文件" @click="emit('fileUploadClick')">📎</button>
        <button
          v-if="hasMessages || IS_TEMPORARY_SESSION"
          :class="isFull
            ? 'shrink-0 text-white/40 hover:text-white bg-transparent border-none cursor-pointer text-sm'
            : 'action-btn'"
          :title="isFull ? undefined : '新建对话'"
          v-on="fullOnlyStop"
          @click="emit('newSession')"
        >
          ➕
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ========== 紧凑态（Everywhere 风格） ========== */
.floating-compact {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: stretch;
  background: #0e1116;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.compact-ball {
  width: 100px;
  height: 100px;
  flex-shrink: 0;
  cursor: pointer;
  position: relative;
  background: radial-gradient(circle at 40% 35%, #161b22, #0e1116);
  transition: filter 0.2s ease;
}

.compact-ball:hover {
  filter: brightness(1.08);
}

/* 紧凑/完整态的球无光环，内容占满 */
.compact-ball .ball-content {
  inset: 0;
  background: none;
}

.compact-ball .ball-ring {
  inset: 0;
}

.compact-ball:hover .ball-ring {
  border-color: rgba(255, 255, 255, 0.4);
}

.ball-content {
  position: absolute;
  border-radius: 50%;
  overflow: hidden;
  z-index: 1;
}

.ball-ring {
  position: absolute;
  border-radius: 50%;
  border: 1.5px solid rgba(255, 255, 255, 0.12);
  z-index: 2;
  pointer-events: none;
  transition: border-color 0.3s;
}

.ball-frame {
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
  user-select: none;
  -webkit-user-drag: none;
}

/* ========== 操作按钮 ========== */
.action-btn {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.2s, background-color 0.2s;
  white-space: nowrap;
}

.action-btn:hover {
  color: rgba(255, 255, 255, 0.8);
  background-color: rgba(255, 255, 255, 0.08);
}

.action-btn.active {
  color: rgba(255, 255, 255, 0.8);
}

/* ========== 快捷技能标签 ========== */
.skill-tag {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 10px;
  transition: color 0.2s, background-color 0.2s, border-color 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}

.skill-tag:hover {
  color: rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.25);
}

.skill-tag.active {
  color: rgba(255, 255, 255, 0.95);
  background: rgba(172, 69, 241, 0.25);
  border-color: rgba(172, 69, 241, 0.5);
}

/* ========== 待发送截图指示条 ========== */
.pending-image-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
}

.pending-image-thumb {
  width: 32px;
  height: 18px;
  object-fit: cover;
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  pointer-events: none;
  flex-shrink: 0;
}

.pending-image-remove {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  font-size: 10px;
  padding: 0 4px;
  flex-shrink: 0;
  transition: color 0.15s;
}

.pending-image-remove:hover {
  color: rgba(255, 100, 100, 0.8);
}

/* ========== 内容入场动画 ========== */
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
</style>
