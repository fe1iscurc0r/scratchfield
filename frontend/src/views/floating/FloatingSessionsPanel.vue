<!-- 会话历史面板（卷190-B1：从 FloatingView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { ref } from 'vue'
import { formatRelativeTime } from '@/utils/session'

export interface FloatingSessionItem {
  sessionId: string
  createdAt: string
  lastActiveAt: string
  conversationRounds: number
  temporary: boolean
}

defineProps<{
  sessions: FloatingSessionItem[]
  loading: boolean
  currentSessionId: string | null
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  switch: [id: string]
  delete: [id: string]
}>()

// 根元素暴露给壳：fitWindowHeight 需要测量 offsetHeight（面板展开高度计入窗口拟合）
const rootEl = ref<HTMLElement | null>(null)
defineExpose({ rootEl })
</script>

<template>
  <Transition name="session-fade">
    <div v-if="open" ref="rootEl" class="session-panel" @pointerdown.stop>
      <div class="flex items-center justify-between px-3 py-1.5 border-b border-white/10">
        <span class="text-white/70 text-xs font-bold">对话历史</span>
        <button
          class="text-white/40 hover:text-white/80 bg-transparent border-none cursor-pointer text-xs"
          @click="emit('close')"
        >
          关闭
        </button>
      </div>
      <div class="session-list">
        <div v-if="loading" class="text-white/40 text-xs text-center py-3">
          加载中...
        </div>
        <div v-else-if="sessions.length === 0" class="text-white/40 text-xs text-center py-3">
          暂无历史对话
        </div>
        <div
          v-for="s in sessions" :key="s.sessionId"
          class="session-item"
          :class="{ 'bg-white/10': s.sessionId === currentSessionId }"
          @click="emit('switch', s.sessionId)"
        >
          <div class="flex-1 min-w-0">
            <div class="text-white/80 text-xs truncate">
              <span v-if="s.temporary" class="temporary-tag">临时</span>
              {{ s.sessionId.slice(0, 8) }}...
            </div>
            <div class="text-white/40 text-xs">
              {{ formatRelativeTime(s.lastActiveAt) }} · {{ s.conversationRounds }} 轮
            </div>
          </div>
          <button
            class="text-white/30 hover:text-red-400 bg-transparent border-none cursor-pointer text-xs shrink-0 ml-2"
            title="删除"
            @click.stop="emit('delete', s.sessionId)"
          >
            🗑
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* ========== 会话历史面板 ========== */
.session-panel {
  flex-shrink: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.4);
}

.session-list {
  overflow-y: auto;
  max-height: 12rem;
}

.session-list::-webkit-scrollbar {
  width: 6px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}

.session-list::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

.session-item {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  cursor: pointer;
  transition: background-color 0.15s;
}

.session-item:hover {
  background-color: rgba(255, 255, 255, 0.06);
}

/* ========== 临时会话标记 ========== */
.temporary-tag {
  display: inline-block;
  font-size: 9px;
  padding: 0 4px;
  margin-right: 4px;
  border-radius: 3px;
  background: rgba(255, 165, 0, 0.2);
  color: rgba(255, 165, 0, 0.9);
  border: 1px solid rgba(255, 165, 0, 0.3);
  vertical-align: middle;
  line-height: 14px;
}

/* ========== 会话面板过渡（仅 opacity，不影响布局测量） ========== */
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
