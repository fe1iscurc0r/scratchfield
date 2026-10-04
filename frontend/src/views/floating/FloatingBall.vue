<!-- 悬浮球·球态（卷190-B1：从 FloatingView.vue 纯搬移，template+style 同进退）。
     拖拽/点击/右键事件由壳通过 attrs fallthrough 绑到根元素（handler 在 useFloatingActions）。 -->
<script setup lang="ts">
defineProps<{
  frameIndex: number
  generating: boolean
  notifying: boolean
  lightbulb: boolean
}>()

const framePath = (i: number) => `./assets/悬浮球序列帧/${i}.png`
</script>

<template>
  <div class="floating-ball" @dragstart.prevent>
    <div class="ball-glow" :class="{ 'glow-pulse': generating }" />
    <div class="ball-content">
      <img :src="framePath(frameIndex)" class="ball-frame" draggable="false">
      <img v-if="notifying" :src="framePath(0)" class="ball-frame lightbulb-overlay" :class="{ visible: lightbulb }" draggable="false">
    </div>
    <div class="ball-ring" />
  </div>
</template>

<style scoped>
/* ========== 球态 ========== */
.floating-ball {
  position: relative;
  width: 100px;
  height: 100px;
  border-radius: 50%;
  cursor: pointer;
  touch-action: none;
  transition: filter 0.2s ease;
}

/* 彩色光环（保持在窗口 100x100 内，避免方形裁切） */
.ball-glow {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(from 0deg, #ac45f1, #7a7ef4, #3dc6f8, #55a9f6, #ac45f1);
  opacity: 0.7;
  z-index: 0;
  animation: glow-spin 6s linear infinite;
}

@keyframes glow-spin {
  to { transform: rotate(360deg); }
}

/* 生成中：旋转加速 + 透明度脉冲 */
.ball-glow.glow-pulse {
  animation: glow-spin 3s linear infinite, glow-pulse 1.5s ease-in-out infinite;
}

@keyframes glow-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.ball-content {
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  overflow: hidden;
  z-index: 1;
  background: radial-gradient(circle at 40% 35%, #161b22, #0e1116);
}

.ball-frame {
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
  user-select: none;
  -webkit-user-drag: none;
}

/* 灯泡通知覆盖层：绝对定位叠在眨眼帧上方，独立闪烁 */
.lightbulb-overlay {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.lightbulb-overlay.visible {
  opacity: 1;
}

/* 边框环 */
.ball-ring {
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  border: 1.5px solid rgba(255, 255, 255, 0.12);
  z-index: 2;
  pointer-events: none;
  transition: border-color 0.3s;
}

.floating-ball:hover {
  filter: brightness(1.08);
}

.floating-ball:hover .ball-ring {
  border-color: rgba(255, 255, 255, 0.4);
}

.floating-ball:hover .ball-glow {
  opacity: 0.8;
}
</style>
