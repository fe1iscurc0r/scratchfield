<!-- 窗口截屏选择面板（卷190-B1：从 FloatingView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import type { CaptureSource } from '@/electron.d'
import { ref } from 'vue'

defineProps<{
  sources: CaptureSource[]
  loading: boolean
  permissionDenied: boolean
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  select: [source: CaptureSource]
  openSettings: []
}>()

// 根元素暴露给壳：fitWindowHeight 需要测量 offsetHeight（面板展开高度计入窗口拟合）
const rootEl = ref<HTMLElement | null>(null)
defineExpose({ rootEl })
</script>

<template>
  <Transition name="session-fade">
    <div v-if="open" ref="rootEl" class="capture-panel" @pointerdown.stop>
      <div class="flex items-center justify-between px-3 py-1.5 border-b border-white/10">
        <span class="text-white/70 text-xs font-bold">选择要截取的窗口</span>
        <button
          class="text-white/40 hover:text-white/80 bg-transparent border-none cursor-pointer text-xs"
          @click="emit('close')"
        >
          关闭
        </button>
      </div>
      <div class="capture-grid">
        <div v-if="loading" class="text-white/40 text-xs text-center py-3 col-span-2">
          加载中...
        </div>
        <div v-else-if="permissionDenied" class="text-white/40 text-xs text-center py-3 col-span-2">
          需要屏幕录制权限，请前往<br>系统设置 &gt; 隐私与安全性 &gt; 屏幕录制<br>中授权 scratchpad
          <button class="mt-2 px-3 py-1 rounded bg-white/10 hover:bg-white/20 text-white/60 hover:text-white/80 text-xs border-none cursor-pointer transition-colors" @click="emit('openSettings')">
            打开系统设置
          </button>
        </div>
        <div v-else-if="sources.length === 0" class="text-white/40 text-xs text-center py-3 col-span-2">
          未检测到可截取的窗口<br>
          <span class="text-white/30">可能是屏幕录制权限未授予，请检查<br>系统设置 &gt; 隐私与安全性 &gt; 屏幕录制</span>
          <br>
          <button class="mt-2 px-3 py-1 rounded bg-white/10 hover:bg-white/20 text-white/60 hover:text-white/80 text-xs border-none cursor-pointer transition-colors" @click="emit('openSettings')">
            打开系统设置
          </button>
        </div>
        <div
          v-for="src in sources" :key="src.id"
          class="capture-item"
          @click="emit('select', src)"
        >
          <img :src="src.thumbnail" class="capture-thumb" draggable="false">
          <span class="capture-name">{{ src.name }}</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* ========== 窗口截屏面板 ========== */
.capture-panel {
  flex-shrink: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.4);
}

.capture-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  padding: 8px;
  overflow-y: auto;
  max-height: 14rem;
}

.capture-grid::-webkit-scrollbar {
  width: 6px;
}

.capture-grid::-webkit-scrollbar-track {
  background: transparent;
}

.capture-grid::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}

.capture-item {
  cursor: pointer;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: border-color 0.15s;
}

.capture-item:hover {
  border-color: rgba(172, 69, 241, 0.5);
}

.capture-thumb {
  width: 100%;
  aspect-ratio: 16/9;
  object-fit: cover;
  pointer-events: none;
  user-select: none;
}

.capture-name {
  display: block;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.6);
  padding: 2px 6px 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 面板过渡（仅 opacity，不影响布局测量；与 SessionsPanel 同名同参数） */
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
